"""
jarvis/input/voice_input.py
============================
Single-stream voice input:
  - Wake-word detection via Vosk (lightweight, always on)
  - VAD-based command recording: stops when user stops talking
  - High-accuracy transcription via Faster-Whisper
  - Live partials shown in HUD overlay
"""

import os
import json
import logging
import queue
import threading
import urllib.request
import zipfile
import time

import collections
import numpy as np
import sounddevice as sd
from pathlib import Path


class VoiceInputSystem:
    """
    One persistent RawInputStream shared between wake-word detection
    and command recording. Mode toggles atomically so no double-open occurs.
    """

    _MODE_WAKE   = "wake"    # Vosk listening for "jarvis"
    _MODE_RECORD = "record"  # collecting audio for Whisper
    _MODE_IDLE   = "idle"

    def __init__(self, config: dict):
        self.config  = config
        self.logger  = logging.getLogger("Jarvis.VoiceInput")

        self.vosk_model_dir     = Path(config["voice"]["vosk_model_dir"])
        self.whisper_model_name = config["voice"]["whisper_model"]

        self._overlay      = None
        self._voice_out    = None   # For barge-in interrupt
        self.vosk_rec      = None
        self.whisper_model = None

        # Shared audio queue (raw bytes from sounddevice)
        self._audio_q   = queue.Queue(maxsize=400)
        self._mode      = self._MODE_IDLE
        self._mode_lock = threading.Lock()

        self._preroll_buffer = collections.deque(maxlen=10)

        self.stop_listening    = threading.Event()
        self._stream_thread    = None

        # Detect native mic sample rate
        self._device_idx, self._native_sr = self._detect_mic()

        self._bootstrap_vosk()

    # ── Public API ────────────────────────────────────────────────────────

    def set_overlay(self, overlay):
        """Wire HUD overlay so live partials appear while speaking."""
        self._overlay = overlay

    def set_voice_out(self, voice_out):
        """Wire TTS so barge-in can call voice_out.interrupt()."""
        self._voice_out = voice_out

    def set_system(self, system):
        """Wire system reference for plan abort control."""
        self._system = system

    def init_whisper(self):
        """Public alias — pre-load Whisper from external code."""
        self._init_whisper()

    # ── Device detection ──────────────────────────────────────────────────

    def _detect_mic(self):
        try:
            dev = sd.query_devices(kind='input')
            idx = dev['index']
            sr  = int(dev['default_samplerate'])
            self.logger.info(f"Mic [{idx}] {dev['name']} @ {sr} Hz")
            return idx, sr
        except Exception as e:
            self.logger.warning(f"Mic detection failed: {e}. Using defaults.")
            return None, 44100

    # ── Model bootstrap ───────────────────────────────────────────────────

    def _bootstrap_vosk(self):
        if not self.vosk_model_dir.exists():
            self.logger.info("Downloading Vosk model…")
            os.makedirs(self.vosk_model_dir.parent, exist_ok=True)
            zip_path = self.vosk_model_dir.parent / "vosk-model.zip"
            url = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
            try:
                print(f"Downloading Vosk from {url}…")
                urllib.request.urlretrieve(url, zip_path)
                with zipfile.ZipFile(zip_path, 'r') as z:
                    z.extractall(self.vosk_model_dir.parent)
                extracted = self.vosk_model_dir.parent / "vosk-model-small-en-us-0.15"
                if extracted.exists():
                    os.rename(extracted, self.vosk_model_dir)
                if zip_path.exists():
                    os.remove(zip_path)
                print("Vosk model ready.")
            except Exception as e:
                self.logger.error(f"Vosk download failed: {e}")

    def _init_vosk(self):
        if self.vosk_rec is not None:
            return
        try:
            from vosk import Model, KaldiRecognizer
            self.logger.info(f"Loading Vosk from '{self.vosk_model_dir}'…")
            model = Model(str(self.vosk_model_dir))
            self.vosk_rec = KaldiRecognizer(model, 16000)
            self.logger.info("Vosk ready.")
        except Exception as e:
            self.logger.error(f"Vosk init failed: {e}")

    def _init_whisper(self):
        if self.whisper_model is not None:
            return
        try:
            from faster_whisper import WhisperModel
            import torch
            device       = "cuda" if torch.cuda.is_available() else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"
            self.logger.info(
                f"Loading Whisper '{self.whisper_model_name}' on {device}…")
            self.whisper_model = WhisperModel(
                self.whisper_model_name,
                device=device, compute_type=compute_type)
            self.logger.info("Whisper ready.")
        except Exception as e:
            self.logger.error(f"Whisper init failed: {e}")

    # ── Audio helpers ─────────────────────────────────────────────────────

    def _to_16k(self, audio_int16: np.ndarray) -> bytes:
        """Resample int16 PCM from native rate → 16 kHz for Vosk."""
        if self._native_sr == 16000:
            return audio_int16.tobytes()
        ratio   = 16000 / self._native_sr
        new_len = max(1, int(len(audio_int16) * ratio))
        out = np.interp(
            np.linspace(0, len(audio_int16) - 1, new_len),
            np.arange(len(audio_int16)),
            audio_int16.astype(np.float32)
        ).astype(np.int16)
        return out.tobytes()

    def _stream_callback(self, indata, frames, time_info, status):
        """sounddevice callback — drops audio if queue is full."""
        if status:
            self.logger.debug(f"Audio status: {status}")
        try:
            self._audio_q.put_nowait(bytes(indata))
        except queue.Full:
            pass

    # ── Stream management ─────────────────────────────────────────────────

    def _start_stream(self):
        block_frames = int(self._native_sr * 0.20)   # 200 ms per block
        self._sd_stream = sd.RawInputStream(
            samplerate  = self._native_sr,
            blocksize   = block_frames,
            dtype       = 'int16',
            channels    = 1,
            device      = self._device_idx,
            callback    = self._stream_callback,
        )
        self._sd_stream.start()
        self.logger.info("Audio stream started.")

    def _stop_stream(self):
        try:
            self._sd_stream.stop()
            self._sd_stream.close()
        except Exception:
            pass

    def _flush_queue(self):
        """Drain all pending audio from the queue."""
        while not self._audio_q.empty():
            try:
                self._audio_q.get_nowait()
            except queue.Empty:
                break

    # ── Wake-word listener ────────────────────────────────────────────────

    def _is_wake_word(self, text: str) -> bool:
        t = text.lower()
        # Phonetic synonyms of Jarvis to ensure high reliability and capture it clearly
        wake_words = ["jarvis", "javis", "jarves", "travis", "garvis", "charvis", "gervais", "arrives", "jaffas", "jobless", "yahweh", "serves", "service"]
        return any(w in t for w in wake_words)

    def listen_for_wakeword(self, callback_func):
        """
        Start background listener for 'jarvis'.
        All audio comes from ONE shared stream.
        When detected, switch to RECORD mode → call callback → return to WAKE.
        """
        self._init_vosk()
        self._init_whisper()   # pre-load now so first command is instant

        if not self.vosk_rec:
            self.logger.error("Vosk not ready — cannot start wake-word listener.")
            return

        self._mode = self._MODE_WAKE

        def _loop():
            self.logger.info("Wake-word listener active. Say 'Jarvis'…")
            self._start_stream()
            try:
                while not self.stop_listening.is_set():
                    with self._mode_lock:
                        cur = self._mode

                    if cur == self._MODE_WAKE:
                        try:
                            raw = self._audio_q.get(timeout=0.5)
                        except queue.Empty:
                            continue

                        # Store in pre-roll buffer
                        self._preroll_buffer.append(raw)

                        pcm   = np.frombuffer(raw, dtype=np.int16)
                        pcm16 = self._to_16k(pcm)

                        if self.vosk_rec.AcceptWaveform(pcm16):
                            res  = json.loads(self.vosk_rec.Result())
                            text = res.get("text", "").strip()
                            if text and self._overlay:
                                self._overlay.clear_live_text()
                            if text and self._is_wake_word(text):
                                self.logger.info(f"Wake word 'Jarvis' detected in full result: '{text}'")
                                self._trigger_command(callback_func)
                        else:
                            # Show live partial in HUD if not sleeping and wake word matches or is spoken
                            p = json.loads(
                                self.vosk_rec.PartialResult()
                            ).get("partial", "").strip()
                            if p:
                                is_sleeping = (self._overlay is not None and self._overlay._state == "sleeping")
                                if self._is_wake_word(p):
                                    self.logger.info(f"Wake word 'Jarvis' detected in partial result: '{p}'")
                                    self._trigger_command(callback_func)
                                elif not is_sleeping:
                                    self._overlay.show_live_text(p + "  …")

                    elif cur == self._MODE_RECORD:
                        # ── BARGE-IN: detect 'Jarvis' even while processing ──
                        try:
                            raw = self._audio_q.get(timeout=0.3)
                        except queue.Empty:
                            continue

                        pcm   = np.frombuffer(raw, dtype=np.int16)
                        pcm16 = self._to_16k(pcm)

                        if self.vosk_rec.AcceptWaveform(pcm16):
                            res  = json.loads(self.vosk_rec.Result())
                            text = res.get("text", "").strip()
                            if self._is_wake_word(text):
                                self.logger.info("Barge-in detected! Interrupting Jarvis.")
                                if self._voice_out:
                                    self._voice_out.interrupt()
                                if hasattr(self, "_system") and self._system:
                                    self._system.execution_engine.abort()
                                if self._overlay:
                                    self._overlay.show_live_text("…listening…")

            except Exception as e:
                self.logger.error(f"Wake-word loop error: {e}", exc_info=True)
            finally:
                self._stop_stream()

        self._stream_thread = threading.Thread(
            target=_loop, daemon=True, name="WakeWordListener")
        self._stream_thread.start()

    # ── Trigger command flow ──────────────────────────────────────────────

    def has_active_speech_in_queue(self) -> bool:
        """Check if there is active speech (RMS above threshold) in the queue."""
        SPEECH_RMS = 0.008
        temp_items = []
        has_speech = False
        while not self._audio_q.empty():
            try:
                raw = self._audio_q.get_nowait()
                temp_items.append(raw)
                raw_np = np.frombuffer(raw, dtype=np.int16)
                rms = float(np.sqrt(np.mean((raw_np.astype(np.float32) / 32768.0) ** 2)))
                if rms >= SPEECH_RMS:
                    has_speech = True
            except queue.Empty:
                break
        # Put items back
        for item in temp_items:
            self._audio_q.put(item)
        return has_speech

    def _trigger_command(self, callback_func):
        """
        Switch to RECORD mode, call the callback (which speaks + records),
        then return to WAKE mode. All on the same shared audio stream.
        """
        with self._mode_lock:
            self._mode = self._MODE_RECORD

        # Only flush the queue if there is no active speech (preserves single-breath commands)
        if not self.has_active_speech_in_queue():
            self._flush_queue()
        else:
            self.logger.info("Preserving active user speech in the queue for single-breath processing.")

        try:
            callback_func()
        finally:
            with self._mode_lock:
                self._mode = self._MODE_WAKE
            if self.vosk_rec:
                self.vosk_rec.Reset()
            if self._overlay:
                self._overlay.clear_live_text()

    # ── VAD-based command recording + Whisper transcription ───────────────

    def record_and_transcribe(self, duration: int = 20, bypass_delay: bool = False) -> str:
        """
        Record audio from the shared stream until:
          - 1.5 s of continuous silence after speech began, OR
          - max `duration` seconds elapsed
        Then transcribe with Faster-Whisper.
        Shows live Vosk partials in HUD while recording.
        """
        self._init_whisper()
        if not self.whisper_model:
            self.logger.error("Whisper not loaded — cannot transcribe.")
            return ""

        SPEECH_RMS           = 0.008   # RMS ≥ this = speech

        if not bypass_delay:
            # Wait briefly for TTS audio to finish playing (so we don't
            # record Jarvis's own voice as the command)
            time.sleep(0.20)
            
            # Check if there is active user speech in the queue instead of blindly flushing
            temp_items = []
            has_speech = False
            while not self._audio_q.empty():
                try:
                    raw = self._audio_q.get_nowait()
                    temp_items.append(raw)
                    raw_np = np.frombuffer(raw, dtype=np.int16)
                    rms = float(np.sqrt(np.mean((raw_np.astype(np.float32) / 32768.0) ** 2)))
                    if rms >= SPEECH_RMS:
                        has_speech = True
                except queue.Empty:
                    break
            
            if has_speech:
                self.logger.info("Speech detected in queue during wait delay — retaining audio instead of flushing.")
                for item in temp_items:
                    self._audio_q.put(item)
            else:
                self.logger.info("No speech detected in queue during wait delay — flushing queue.")

        fs           = self._native_sr
        block_ms     = 200                               # 200 ms per chunk
        max_blocks   = int(duration * 1000 / block_ms)

        # Voice Activity Detection thresholds and silence timeout config
        SILENCE_SECS         = self.config["voice"].get("silence_timeout", 2.5)   # stop after this many silent seconds
        silence_blocks_needed = int(SILENCE_SECS * 1000 / block_ms)  # = 12-13 blocks for 2.5s

        chunks         = []
        speech_started = False
        silence_count  = 0
        partial_words  = []

        # Prepend pre-roll buffer if we have any
        if hasattr(self, "_preroll_buffer"):
            while self._preroll_buffer:
                raw = self._preroll_buffer.popleft()
                chunks.append(np.frombuffer(raw, dtype=np.int16))
            if chunks:
                speech_started = True

        self.logger.info(
            f"VAD recording (max {duration}s, stops after {SILENCE_SECS}s silence)…")

        for _ in range(max_blocks):
            if self.stop_listening.is_set():
                break
            try:
                raw = self._audio_q.get(timeout=0.4)
            except queue.Empty:
                if speech_started:
                    silence_count += 2   # timeout = silence
                    if silence_count >= silence_blocks_needed:
                        break
                continue

            raw_np = np.frombuffer(raw, dtype=np.int16)
            rms    = float(np.sqrt(
                np.mean((raw_np.astype(np.float32) / 32768.0) ** 2)))

            if rms >= SPEECH_RMS:
                speech_started = True
                silence_count  = 0
            elif speech_started:
                silence_count += 1
                if silence_count >= silence_blocks_needed:
                    self.logger.info("Silence detected — done recording.")
                    break

            # Accumulate audio once speech begins
            if speech_started:
                chunks.append(raw_np)

            # Live Vosk partials in HUD
            if speech_started and self.vosk_rec and self._overlay:
                pcm16 = self._to_16k(raw_np)
                if self.vosk_rec.AcceptWaveform(pcm16):
                    r = json.loads(self.vosk_rec.Result())
                    t = r.get("text", "").strip()
                    if t:
                        partial_words.append(t)
                        self._overlay.show_live_text(" ".join(partial_words))
                else:
                    p = json.loads(
                        self.vosk_rec.PartialResult()
                    ).get("partial", "").strip()
                    if p:
                        base = " ".join(partial_words)
                        self._overlay.show_live_text(
                            (base + " " if base else "") + p + "  …")

        if not speech_started or not chunks:
            self.logger.info("No speech detected.")
            return ""

        # ── Combine & resample to 16 kHz for Whisper ──────────────────────
        audio_native = np.concatenate(chunks).astype(np.float32) / 32768.0
        if fs != 16000:
            tgt = max(1, int(len(audio_native) * 16000 / fs))
            audio_16k = np.interp(
                np.linspace(0, len(audio_native) - 1, tgt),
                np.arange(len(audio_native)),
                audio_native
            ).astype(np.float32)
        else:
            audio_16k = audio_native

        dur_sec = len(audio_16k) / 16000
        self.logger.info(f"Transcribing {dur_sec:.1f}s with Whisper…")

        try:
            segments, _ = self.whisper_model.transcribe(
                audio_16k,
                language                   = "en",
                beam_size                  = 5,
                vad_filter                 = False,   # we already do VAD above
                no_speech_threshold        = 0.6,
                temperature                = 0.0,     # deterministic
                condition_on_previous_text = False,
                initial_prompt             = "User command for Jarvis AI:",
            )
            raw_text = " ".join(s.text for s in segments).strip()

            # Remove consecutive duplicate words (Whisper repetition artifact)
            words, prev, deduped = raw_text.split(), None, []
            for w in words:
                if w != prev:
                    deduped.append(w)
                prev = w
            transcription = " ".join(deduped)

            self.logger.info(f"Whisper result: '{transcription}'")
            if self._overlay and transcription:
                self._overlay.show_live_text(transcription)
            return transcription

        except Exception as e:
            self.logger.error(f"Whisper error: {e}")
            return ""

    # ── Cleanup ───────────────────────────────────────────────────────────

    def close(self):
        """Signal all threads to stop."""
        self.stop_listening.set()
