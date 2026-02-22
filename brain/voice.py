# =====================================================
# VOICE ENGINE (WAKE + LISTEN + SPEAK) - FINAL STABLE
# =====================================================

import queue
import json
import sounddevice as sd
from vosk import Model, KaldiRecognizer
import pyttsx3
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
# TEXT CLEANER
# =========================================
def clean_command(text):
    text = text.lower()

    replacements = {
        " dot ": ".",
        " dot": ".",
        "dot ": ".",
        " slash ": "/",
        " backslash ": "\\",
        " dot py": ".py",
        " dot exe": ".exe",
        " dot txt": ".txt",
        " dot json": ".json",
    }

    for k, v in replacements.items():
        text = text.replace(k, v)

    ignore = ["the", "a", "an", "is", "to", "can", "you", "please"]

    words = text.split()
    filtered = [w for w in words if w not in ignore]

    return " ".join(filtered).strip()


# =========================================
# 🔊 TTS ENGINE (FINAL FIX - QUEUE BASED)
# =========================================
engine = None
tts_queue = queue.Queue()
is_speaking = False


def init_tts():
    global engine

    if engine is None:
        engine = pyttsx3.init("sapi5")  # Windows stable engine
        engine.setProperty('rate', 170)
        engine.setProperty('volume', 1.0)

        voices = engine.getProperty('voices')
        if voices:
            engine.setProperty('voice', voices[0].id)

        # 🔥 Start background TTS worker
        threading.Thread(target=_tts_worker, daemon=True).start()


def _tts_worker():
    global is_speaking

    while True:
        text = tts_queue.get()

        if text is None:
            continue

        try:
            is_speaking = True

            engine.stop()
            engine.say(text)
            engine.runAndWait()

        except Exception as e:
            print("TTS ERROR:", e)

        finally:
            is_speaking = False
            tts_queue.task_done()


def speak(text):
    if not text:
        return

    def run():
        global is_speaking

        try:
            is_speaking = True

            # 🔥 FULL RESET ENGINE EVERY TIME (fix silent bug)
            engine = pyttsx3.init("sapi5")

            engine.setProperty('rate', 170)
            engine.setProperty('volume', 1.0)

            voices = engine.getProperty('voices')
            if voices:
                engine.setProperty('voice', voices[0].id)

            engine.say(text)
            engine.runAndWait()

            engine.stop()
            del engine  # 🔥 force cleanup

        except Exception as e:
            print("TTS ERROR:", e)

        finally:
            is_speaking = False

    threading.Thread(target=run, daemon=True).start()


# =========================================
# AUDIO CALLBACK
# =========================================
def callback(indata, frames, time_info, status):
    if status:
        print("⚠ Audio:", status)
    q.put(bytes(indata))


# =========================================
# CLEAR AUDIO QUEUE
# =========================================
def clear_queue():
    while not q.empty():
        try:
            q.get_nowait()
        except:
            break


# =========================================
# WAKE WORD LISTENER
# =========================================
def listen_for_wake():
    print("🎙 Say 'Jarvis'...")

    clear_queue()

    with sd.RawInputStream(
        samplerate=16000,
        blocksize=4000,
        dtype="int16",
        channels=1,
        callback=callback
    ):
        while True:
            data = q.get()

            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                text = result.get("text", "").lower()

                if "jarvis" in text:
                    print("✅ Wake detected")
                    speak("Yes?")
                    return True


# =========================================
# 🎧 CONTINUOUS LISTEN (UNCHANGED)
# =========================================
def listen_continuous():
    print("🎧 Listening... (say 'exit' to stop)")

    clear_queue()

    stream = sd.RawInputStream(
        samplerate=16000,
        blocksize=2000,
        dtype="int16",
        channels=1,
        callback=callback
    )

    last_text = ""
    last_command = ""
    silence_timer = None
    silence_threshold = 1.0

    with stream:
        while True:
            data = q.get()

            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                text = result.get("text", "").strip()

                if text:
                    last_text = text
                    silence_timer = time.time()

            if last_text and silence_timer:
                if time.time() - silence_timer > silence_threshold:

                    cleaned = clean_command(last_text)

                    if not cleaned or len(cleaned) < 2:
                        last_text = ""
                        continue

                    if cleaned == last_command:
                        last_text = ""
                        continue

                    last_command = cleaned

                    print(f"You (voice): {cleaned}")

                    stream.stop()

                    if "exit" in cleaned:
                        speak("Going to sleep")
                        return "__EXIT__"

                    return cleaned