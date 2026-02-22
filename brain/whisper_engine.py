# =====================================================
# WHISPER ENGINE (FINAL ULTRA STABLE VERSION)
# =====================================================

import whisper
import sounddevice as sd
import numpy as np
import time

print("🔄 Loading Whisper model...")
model = whisper.load_model("base")


# =========================================
# SETTINGS
# =========================================
TARGET_SAMPLE_RATE = 16000
SILENCE_THRESHOLD = 0.01
SILENCE_DURATION = 1.5
MIN_AUDIO_LENGTH = 0.7
SAMPLE_RATE = 16000

# =========================================
# AUTO DEVICE SELECT (🔥 FIX)
# =========================================
def get_working_device():
    devices = sd.query_devices()

    for i, d in enumerate(devices):
        if d["max_input_channels"] > 0:
            try:
                sd.check_input_settings(device=i, samplerate=16000)
                print(f"✅ Using device {i}: {d['name']}")
                return i, 16000
            except:
                try:
                    sd.check_input_settings(device=i, samplerate=44100)
                    print(f"✅ Using device {i}: {d['name']} (44100Hz)")
                    return i, 44100
                except:
                    continue

    raise RuntimeError("❌ No working microphone found")


DEVICE_INDEX, RECORD_SAMPLE_RATE = get_working_device()


# =========================================
# RESAMPLE
# =========================================
def resample_audio(audio, original_sr, target_sr):
    duration = len(audio) / original_sr
    new_length = int(duration * target_sr)

    return np.interp(
        np.linspace(0, len(audio), new_length),
        np.arange(len(audio)),
        audio
    ).astype(np.float32)


# =========================================
# RECORD AUDIO
# =========================================
def record_audio():

    print("🎙 Speak...")

    audio_data = []
    silence_start = None
    speaking = False
    stop_recording = False

    start_time = time.time()
    MAX_WAIT_FOR_SPEECH = 5      # wait max 5 sec for user to start
    MAX_RECORD_TIME = 15         # hard limit

    def callback(indata, frames, time_info, status):
        nonlocal silence_start, speaking, stop_recording

        if status:
            print("⚠ Audio:", status)

        # 🔥 BETTER VOLUME DETECTION (RMS)
        volume = np.sqrt(np.mean(indata**2))

        # 🎤 SPEECH DETECTED
        if volume > 0.02:   # 🔥 tuned threshold (IMPORTANT)
            speaking = True
            silence_start = None
            audio_data.append(indata.copy())

        # 🤫 SILENCE AFTER SPEECH
        elif speaking:
            audio_data.append(indata.copy())

            if silence_start is None:
                silence_start = time.time()

            elif time.time() - silence_start > SILENCE_DURATION:
                stop_recording = True

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        device=1,  # 🔥 FORCE REAL MICROPHONE (NOT mapper)
        callback=callback
    )

    stream.start()

    while not stop_recording:

        # ❌ USER NEVER SPOKE
        if not speaking and time.time() - start_time > MAX_WAIT_FOR_SPEECH:
            stream.stop()
            stream.close()
            print("⚠ No speech detected (timeout)")
            return None

        # ❌ SAFETY LIMIT
        if time.time() - start_time > MAX_RECORD_TIME:
            stop_recording = True

        sd.sleep(100)

    stream.stop()
    stream.close()

    # 🔥 CRITICAL FIX (release audio device)
    time.sleep(0.5)

    print("🛑 Recording stopped")

    if not audio_data:
        return None

    audio = np.concatenate(audio_data, axis=0)

    if len(audio.shape) > 1:
        audio = audio[:, 0]

    duration = len(audio) / RECORD_SAMPLE_RATE
    if duration < MIN_AUDIO_LENGTH:
        return None

    # 🔁 RESAMPLE IF NEEDED
    if RECORD_SAMPLE_RATE != TARGET_SAMPLE_RATE:
        audio = resample_audio(audio, RECORD_SAMPLE_RATE, TARGET_SAMPLE_RATE)

    return audio


# =========================================
# TRANSCRIBE
# =========================================
def transcribe_audio():

    audio = record_audio()

    if audio is None:
        return ""

    print("🧠 Transcribing with Whisper...")

    try:
        result = model.transcribe(audio, fp16=False)
        text = result["text"].strip()

        print(f"You (whisper): {text}")
        return text

    except Exception as e:
        print("Whisper error:", e)
        return ""