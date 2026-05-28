import os
import re
import asyncio
import logging
import subprocess
import urllib.request
import zipfile
import threading
import tempfile
from pathlib import Path


class VoiceOutputSystem:
    """
    TTS with 3-tier priority:
      1. edge-tts  (Microsoft Neural — sounds very natural, online)
      2. Piper     (local offline fallback)
      3. SAPI5     (Windows built-in last resort)

    Supports mid-word interrupt() for barge-in.
    """

    # Microsoft Neural voice — sounds clear and natural
    EDGE_VOICE = "en-US-GuyNeural"      # calm male voice
    # Alternatives: "en-US-AriaNeural" (female), "en-GB-RyanNeural" (British male)

    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger("Jarvis.TTS")
        self.piper_model_path = Path(config["voice"]["piper_model_path"])
        self.use_fallback     = config["voice"]["use_tts_fallback"]
        self.rate_edge        = config["voice"].get("rate_edge", "-10%")
        self.rate_piper       = config["voice"].get("rate_piper", 1.15)
        self.rate_sapi        = config["voice"].get("rate_sapi", 150)

        self._overlay    = None
        self._tts_lock   = threading.Lock()
        self.piper_exec  = None

        # Barge-in interrupt flag
        self._interrupt  = threading.Event()

        # Cache directory setup
        self.cache_dir = self.piper_model_path.parent.parent.parent / "cache"
        os.makedirs(self.cache_dir, exist_ok=True)

        self._bootstrap_piper()

    def set_overlay(self, overlay):
        self._overlay = overlay

    def interrupt(self):
        """Stop any currently playing speech (barge-in)."""
        self._interrupt.set()

    def clear_interrupt(self):
        self._interrupt.clear()

    # ── Piper bootstrap (offline fallback) ───────────────────────────────

    def _bootstrap_piper(self):
        piper_dir = self.piper_model_path.parent
        os.makedirs(piper_dir, exist_ok=True)

        if not self.piper_model_path.exists():
            self.logger.info("Piper voice model not found. Downloading...")
            model_url  = (
                "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
                "en/en_US/ryan/medium/en_US-ryan-medium.onnx")
            config_url = model_url + ".json"
            try:
                urllib.request.urlretrieve(model_url, self.piper_model_path)
                urllib.request.urlretrieve(config_url,
                                           str(self.piper_model_path) + ".json")
            except Exception as e:
                self.logger.error(f"Failed to download Piper model: {e}")

        bin_dir         = piper_dir.parent.parent / "bin" / "piper"
        self.piper_exec = bin_dir / "piper.exe"

        if not self.piper_exec.exists():
            os.makedirs(bin_dir, exist_ok=True)
            zip_path = bin_dir.parent / "piper.zip"
            url = ("https://github.com/rhasspy/piper/releases/download/"
                   "2023.11.14-2/piper_windows_amd64.zip")
            try:
                urllib.request.urlretrieve(url, zip_path)
                with zipfile.ZipFile(zip_path, "r") as z:
                    z.extractall(bin_dir.parent)
                if zip_path.exists():
                    os.remove(zip_path)
            except Exception as e:
                self.logger.error(f"Failed to bootstrap Piper binary: {e}")

    # ── Public API ────────────────────────────────────────────────────────

    def speak(self, text: str, block: bool = True):
        """
        Speak text using edge-tts → Piper → SAPI5.
        Supports interrupt() for barge-in and pause/resume continuation.
        Uses local cache & pipeline pre-fetching to prevent latency pauses.
        """
        # Convert currency symbols to spoken words
        text = text.replace("₹", "Rupees ")
        clean_text = self._clean_speech_text(text)
        if not clean_text:
            return

        self._interrupt.clear()

        try:
            print(f"\n[Jarvis]: {text}\n")
        except UnicodeEncodeError:
            import sys
            safe_text = text.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding)
            print(f"\n[Jarvis]: {safe_text}\n")

        if self._overlay:
            self._overlay.set_state("speaking")
            self._overlay.show_text(text)
            self._overlay.reset_sleep_timer()

        # Split into sentences for fine-grained pause/resume
        import re
        sentence_delimiters = re.compile(r'(?<=[.!?])\s+')
        sentences = [s.strip() for s in sentence_delimiters.split(clean_text) if s.strip()]
        self._interrupted_remaining = []

        def _run():
            import time
            import hashlib
            for idx, sentence in enumerate(sentences):
                if self._interrupt.is_set():
                    self._interrupted_remaining = sentences[idx:]
                    break

                # Rolling background pre-fetch for the next sentence
                if idx + 1 < len(sentences):
                    next_sentence = sentences[idx+1]
                    threading.Thread(
                        target=self._prefetch_sentence,
                        args=(next_sentence,),
                        daemon=True,
                        name=f"TTS-Prefetch-{idx+1}"
                    ).start()

                # Clean the current sentence
                sentence_clean = self._clean_speech_text(sentence)
                if not sentence_clean:
                    continue

                # Compute cache path
                hash_input = f"{sentence_clean}_{self.EDGE_VOICE}_{self.rate_edge}_{self.rate_piper}_{self.rate_sapi}".encode("utf-8")
                h = hashlib.md5(hash_input).hexdigest()
                cache_mp3 = self.cache_dir / f"{h}.mp3"
                cache_wav = self.cache_dir / f"{h}.wav"

                success = False
                
                # Check cache hits first
                if cache_mp3.exists() and cache_mp3.stat().st_size > 0:
                    self._play_mp3_interruptible(cache_mp3)
                    success = True
                elif cache_wav.exists() and cache_wav.stat().st_size > 0:
                    self._play_wav_interruptible(cache_wav)
                    success = True
                else:
                    # Cache miss: Synthesize and save directly to cache
                    success = self._synthesize_edge_tts_to_file(sentence_clean, cache_mp3)
                    if success:
                        self._play_mp3_interruptible(cache_mp3)
                    else:
                        success = self._synthesize_piper_to_file(sentence_clean, cache_wav)
                        if success:
                            self._play_wav_interruptible(cache_wav)

                if not success:
                    # Tier 3: SAPI5 fallback (direct speech, no cache)
                    self._speak_sapi5(sentence_clean)

                # Check interrupt immediately after speaking the sentence
                if self._interrupt.is_set():
                    self._interrupted_remaining = sentences[idx+1:]
                    break
                    
                # Natural brief pause between sentences
                time.sleep(0.12)

            if self._overlay:
                self._overlay.clear_live_text()
                self._overlay.set_state("idle")

        if block:
            _run()
        else:
            threading.Thread(target=_run, daemon=True).start()

    def _prefetch_sentence(self, sentence: str):
        """Background thread worker to synthesize and cache a sentence before it is played."""
        import hashlib
        sentence_clean = self._clean_speech_text(sentence)
        if not sentence_clean:
            return

        hash_input = f"{sentence_clean}_{self.EDGE_VOICE}_{self.rate_edge}_{self.rate_piper}_{self.rate_sapi}".encode("utf-8")
        h = hashlib.md5(hash_input).hexdigest()
        cache_mp3 = self.cache_dir / f"{h}.mp3"
        cache_wav = self.cache_dir / f"{h}.wav"

        if cache_mp3.exists() or cache_wav.exists():
            return

        try:
            success = self._synthesize_edge_tts_to_file(sentence_clean, cache_mp3)
            if not success:
                self._synthesize_piper_to_file(sentence_clean, cache_wav)
        except Exception as e:
            self.logger.warning(f"Background prefetch failed for '{sentence_clean}': {e}")

    # ── Tier 1: edge-tts (Microsoft Neural) ───────────────────────────────

    def _synthesize_edge_tts_to_file(self, text: str, output_path: Path) -> bool:
        """Synthesise with edge-tts and save output to output_path."""
        try:
            import edge_tts
            import asyncio

            async def _synthesise():
                communicate = edge_tts.Communicate(text, self.EDGE_VOICE, rate=self.rate_edge)
                await communicate.save(str(output_path))

            # Run inside a dedicated background thread to prevent loop conflict errors
            def _run_synthesis():
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(_synthesise())
                finally:
                    loop.close()

            t = threading.Thread(target=_run_synthesis)
            t.start()
            t.join()

            return output_path.exists() and output_path.stat().st_size > 0
        except Exception as e:
            self.logger.warning(f"edge-tts synthesis failed: {e}")
            return False

    # ── Tier 2: Piper (offline) ────────────────────────────────────────────

    def _synthesize_piper_to_file(self, text: str, output_path: Path) -> bool:
        """Synthesise with Piper and save output to output_path."""
        use_piper = (
            self.piper_exec is not None
            and self.piper_exec.exists()
            and self.piper_model_path.exists()
        )
        if not use_piper:
            return False
        try:
            cmd = [
                str(self.piper_exec),
                "--model", str(self.piper_model_path),
                "--output_file", str(output_path),
                "--length_scale", str(self.rate_piper)
            ]
            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            proc.communicate(input=text.encode("utf-8"))
            proc.wait()
            return output_path.exists() and output_path.stat().st_size > 0
        except Exception as e:
            self.logger.error(f"Piper synthesis failed: {e}")
            return False

    # ── Tier 3: SAPI5 fallback ─────────────────────────────────────────────

    def _speak_sapi5(self, text: str):
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", self.rate_sapi)
            for v in engine.getProperty("voices"):
                if "david" in v.name.lower() or "english" in v.name.lower():
                    engine.setProperty("voice", v.id)
                    break
            engine.say(text)
            engine.runAndWait()
            try:
                engine.stop()
            except Exception:
                pass
        except Exception as e:
            self.logger.error(f"SAPI5 TTS failed: {e}")

    # ── Interruptible MP3 playback (edge-tts output) ───────────────────────

    def _play_mp3_interruptible(self, mp3_path: Path):
        """
        Decode MP3 → float32 PCM and stream through OutputStream.
        Checks interrupt every 100 ms.
        """
        try:
            import soundfile as sf
            import sounddevice as sd
            import numpy as np

            # Try soundfile first (handles MP3 if libsndfile has MP3 support)
            try:
                data, fs = sf.read(str(mp3_path), always_2d=True)
            except Exception:
                # Fallback: use pydub to decode MP3 → wav in memory
                data, fs = self._decode_mp3_pydub(mp3_path)
                if data is None:
                    raise RuntimeError("MP3 decode failed")

            self._stream_audio(data, fs)

        except Exception as e:
            self.logger.error(f"MP3 playback failed: {e}")
            # Try pygame or OS player as last resort
            self._play_with_os(mp3_path)

    def _decode_mp3_pydub(self, mp3_path: Path):
        """Decode MP3 using pydub → numpy float32."""
        try:
            from pydub import AudioSegment
            import numpy as np
            seg = AudioSegment.from_mp3(str(mp3_path))
            fs  = seg.frame_rate
            raw = np.array(seg.get_array_of_samples(), dtype=np.float32)
            raw /= 2 ** (seg.sample_width * 8 - 1)   # normalise to [-1, 1]
            if seg.channels == 2:
                raw = raw.reshape(-1, 2)
            else:
                raw = raw.reshape(-1, 1)
            return raw, fs
        except Exception as e:
            self.logger.warning(f"pydub decode failed: {e}")
            return None, None

    def _play_with_os(self, path: Path):
        """Play audio file using Windows Media Player (fallback)."""
        try:
            os.startfile(str(path))
            import time
            time.sleep(3)   # rough wait; not interruptible
        except Exception:
            pass

    # ── Interruptible WAV playback ─────────────────────────────────────────

    def _play_wav_interruptible(self, wav_path: Path):
        try:
            import soundfile as sf
            data, fs = sf.read(str(wav_path), always_2d=True)
            self._stream_audio(data, fs)
        except Exception as e:
            self.logger.error(f"WAV playback failed: {e}")

    # ── Core streaming playback ────────────────────────────────────────────

    def _stream_audio(self, data, fs: int):
        """
        Play float32 audio data using sounddevice's native player.
        Checks interrupt status in a sleep loop.
        """
        try:
            import sounddevice as sd
            import time

            sd.play(data, fs)
            total_duration = len(data) / fs
            start_time = time.time()
            while time.time() - start_time < total_duration:
                if self._interrupt.is_set():
                    sd.stop()
                    self.logger.info("TTS interrupted by barge-in.")
                    return
                time.sleep(0.05)
            sd.stop()
        except Exception as e:
            self.logger.error(f"Audio stream error: {e}")

    # ── Text cleaning ──────────────────────────────────────────────────────

    def _clean_speech_text(self, text: str) -> str:
        """Strip markdown and symbols that should not be spoken aloud."""
        text = re.sub(r"```.*?```", "[code block]", text, flags=re.DOTALL)
        text = re.sub(r"`[^`]+`", "", text)
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
        # Remove markdown headers/bullets
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)
        text = (text
                .replace("⚠️", "Warning")
                .replace("❌", "Error")
                .replace("✅", "Success")
                .replace("◈", "")
                .replace("●", "")
                .replace("◉", "")
                .replace("…", "...")
                .replace("→", "to"))
        return text.strip()
