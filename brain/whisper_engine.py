# =========================================
# WHISPER ENGINE (ACCURATE TRANSCRIPTION)
# =========================================

import whisper
import tempfile
import sounddevice as sd
import scipy.io.wavfile as wav
import numpy as np

# Load model once (IMPORTANT)
print("🔄 Loading Whisper model...")
model = whisper.load_model("base")  # you can change to "small" later


def record_audio(duration=4, samplerate=16000):
    """
    Records microphone audio for Whisper
    """
    print("🎙 Recording command...")

    audio = sd.rec(int(duration * samplerate),
                   samplerate=samplerate,
                   channels=1,
                   dtype='int16')

    sd.wait()

    return audio, samplerate


def transcribe_audio():
    """
    Records + Transcribes using Whisper
    """

    audio, sr = record_audio()

    # Save temporary file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav.write(f.name, sr, audio)
        temp_path = f.name

    print("🧠 Transcribing with Whisper...")

    result = model.transcribe(temp_path)

    text = result.get("text", "").strip()

    print(f"You (whisper): {text}")

    return text