import queue
import json
import sounddevice as sd
import pyttsx3
from vosk import Model, KaldiRecognizer
import threading
import time

# =========================================
# LOAD MODEL (WAKE + COMMAND)
# =========================================
print("🔄 Loading voice model...")

MODEL_PATH = "models/vosk-model-en-us-0.22"
model = Model(MODEL_PATH)

recognizer = KaldiRecognizer(model, 16000)
recognizer.SetWords(True)

q = queue.Queue()

# =========================================
# TEXT CLEANER (VERY IMPORTANT)
# Fix file names + remove noise
# =========================================
def clean_command(text):
    text = text.lower()

    # 🔥 FILE NAME FIXES
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

    # 🔥 REMOVE NOISE WORDS
    ignore = ["the", "a", "an", "is", "to", "can", "you", "please", "jarvis"]

    words = text.split()
    filtered = [w for w in words if w not in ignore]

    return " ".join(filtered).strip()


# =========================================
# SAFE TTS ENGINE (NO CRASH / NO LOOP ERROR)
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
# AUDIO CALLBACK (MIC STREAM)
# =========================================
def callback(indata, frames, time_info, status):
    if status:
        print("⚠ Audio:", status)
    q.put(bytes(indata))


# =========================================
# CLEAR QUEUE (IMPORTANT 🔥)
# Prevents old audio causing wrong commands
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
        dtype='int16',
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
                    speak("Yes, I am listening")
                    return True


# =========================================
# CONTINUOUS LISTENING (REAL FIXED VERSION)
# =========================================
def listen_continuous():
    print("🎧 Listening... (say 'exit' to stop)")

    clear_queue()

    stream = sd.RawInputStream(
        samplerate=16000,
        blocksize=2000,   # ⚡ faster response
        dtype='int16',
        channels=1,
        callback=callback
    )

    last_text = ""
    last_command = ""
    silence_timer = None
    silence_threshold = 1.0  # tweak: 0.8–1.2 best

    with stream:
        while True:
            data = q.get()

            # ---------------------------------
            # FULL RESULT ONLY (no partial spam)
            # ---------------------------------
            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                text = result.get("text", "").strip()

                if text:
                    last_text = text
                    silence_timer = time.time()

            # ---------------------------------
            # WAIT FOR USER TO FINISH SPEAKING
            # ---------------------------------
            if last_text and silence_timer:
                if time.time() - silence_timer > silence_threshold:

                    cleaned = clean_command(last_text)

                    # ❌ ignore noise
                    if not cleaned or len(cleaned) < 2:
                        last_text = ""
                        continue

                    # ❌ prevent repeat loop
                    if cleaned == last_command:
                        last_text = ""
                        continue

                    last_command = cleaned

                    print(f"You (voice): {cleaned}")

                    # 🔥 STOP MIC BEFORE RESPONSE
                    stream.stop()

                    # EXIT VOICE MODE
                    if "exit" in cleaned:
                        speak("Shutting down voice mode")
                        return "__EXIT__"

                    return cleaned