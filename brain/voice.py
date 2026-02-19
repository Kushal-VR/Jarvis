import queue
import json
import sounddevice as sd
import pyttsx3
from vosk import Model, KaldiRecognizer
import threading
import time

# =========================================
# LOAD MODEL
# =========================================
print("🔄 Loading voice model...")

MODEL_PATH = "models/vosk-model-en-us-0.22"
model = Model(MODEL_PATH)

recognizer = KaldiRecognizer(model, 16000)
recognizer.SetWords(True)

q = queue.Queue()


# =========================================
# SAFE TTS ENGINE
# =========================================
tts_lock = threading.Lock()

def speak(text):
    try:
        with tts_lock:
            print(f"Jarvis (voice): {text}")

            engine = pyttsx3.init()
            engine.setProperty('rate', 170)

            engine.say(text)
            engine.runAndWait()

            engine.stop()
            del engine

    except Exception as e:
        print("TTS error:", e)


# =========================================
# AUDIO CALLBACK
# =========================================
def callback(indata, frames, time_info, status):
    if status:
        print("⚠ Audio:", status)
    q.put(bytes(indata))


# =========================================
# CLEAN COMMAND
# =========================================
def clean_command(text):
    ignore = ["the", "a", "an", "is", "to", "can", "you", "please"]

    words = text.lower().split()
    filtered = [w for w in words if w not in ignore]

    return " ".join(filtered)


# =========================================
# CONTINUOUS LISTENING (FIXED - NO EARLY TRIGGER)
# =========================================
def listen_continuous():
    print("🎧 Listening... (say 'exit' to stop)")

    stream = sd.RawInputStream(
        samplerate=16000,
        blocksize=2000,
        dtype='int16',
        channels=1,
        callback=callback
    )

    last_text = ""
    last_command = ""
    silence_timer = None
    silence_threshold = 1.0  # 🔥 tweak (0.8–1.5)

    with stream:
        while True:
            data = q.get()

            # ONLY FULL RESULTS (NO PARTIAL TRIGGER)
            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                text = result.get("text", "").strip()

                if text:
                    last_text = text
                    silence_timer = time.time()

            # 🧠 WAIT FOR USER TO FINISH SPEAKING
            if last_text and silence_timer:
                if time.time() - silence_timer > silence_threshold:

                    cleaned = clean_command(last_text)

                    # ignore noise
                    if not cleaned or len(cleaned.split()) < 1:
                        last_text = ""
                        continue

                    # prevent repeat spam
                    if cleaned == last_command:
                        last_text = ""
                        continue

                    last_command = cleaned

                    print(f"You (voice): {cleaned}")

                    stream.stop()

                    if "exit" in cleaned:
                        speak("Shutting down voice mode")
                        return "__EXIT__"

                    return cleaned


# =========================================
# WAKE WORD
# =========================================
def listen_for_wake():
    print("🎙 Say 'Jarvis'...")

    with sd.RawInputStream(
        samplerate=16000,
        blocksize=2000,
        dtype='int16',
        channels=1,
        callback=callback
    ):
        while True:
            try:
                data = q.get(timeout=1)
            except:
                continue

            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                text = result.get("text", "").lower()

                if "jarvis" in text:
                    print("✅ Wake detected")
                    speak("Yes, I am listening")
                    return True
