# =====================================================
# MAIN - FINAL STABLE (WHISPER + INTERRUPT + AUDIO FIX)
# =====================================================

from brain.router import route_command
from brain.voice import (
    listen_for_wake,
    speak,
    init_tts
    
)
from brain.whisper_engine import transcribe_audio
from brain.intent_engine import IntentEngine
from brain.command_normalizer import normalize_command

import logging
import os
import time

from guardian.folder_monitor import start_folder_monitor
import guardian.folder_monitor as folder_monitor


# =========================================
# 🔊 AUDIO RESET (CRITICAL FIX)
# =========================================
def reset_audio():
    try:
        os.system("taskkill /f /im audiodg.exe >nul 2>&1")
    except:
        pass




intent_engine = IntentEngine()


# =========================================
# LOGGING
# =========================================
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    filename="logs/jarvis.log",
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
)

print("\nJarvis booting...")
print("Say 'Jarvis' to activate.")
print("Type 'exit' to quit.\n")

observer = start_folder_monitor()


# =========================================
# MAIN LOOP
# =========================================
while True:

    # =========================================
    # AUTO SECURITY
    # =========================================
    if folder_monitor.burst_detected:
        print("\n🚨 Automatic Security Scan Triggered...\n")

        response = route_command("security scan")

        print("\nJarvis:", response, "\n")

        if isinstance(response, str):
            reset_audio()
            time.sleep(0.2)
            speak(response)

    # =========================================
    # WAKE MODE
    # =========================================
    try:
        print("🎙 Waiting for wake word...")
        wake = listen_for_wake()

        # =========================================
        # ACTIVE MODE
        # =========================================
        if wake:
            reset_audio()
            time.sleep(0.2)
            speak("Yes?")
            last_activity = time.time()

            while True:

                # ⏳ AUTO TIMEOUT
                if time.time() - last_activity > 30:
                    reset_audio()
                    speak("Going to sleep")
                    print("💤 Auto sleep\n")
                    break

                print("🎧 Listening (Whisper)...")

                

                # =========================================
                # 🎙 WHISPER INPUT
                # =========================================
                user_input = transcribe_audio()

                # =========================================
                # SILENCE
                # =========================================
                if not user_input or user_input.strip() == "":
                    print("⚠ No voice detected")
                    continue

                # =========================================
                # NORMALIZE
                # =========================================
                user_input = normalize_command(user_input)
                print("🧹 NORMALIZED:", user_input)

                words = user_input.split()

                # =========================================
                # FILTER NOISE
                # =========================================
                if len(words) < 2 and user_input.lower() not in ["exit", "stop"]:
                    print("⚠ Ignored noise")
                    continue

                strange_chars = sum(1 for c in user_input if not c.isalnum() and c != " ")
                if strange_chars > len(user_input) * 0.3:
                    print("⚠ Ignored garbage input")
                    continue

                if len(set(words)) < len(words) * 0.3:
                    print("⚠ Repetitive noise ignored")
                    continue

                # =========================================
                # REMOVE WAKE WORD (OPTIONAL)
                # =========================================
                wake_words = ["jarvis", "jarvice", "jarviss", "jarviz"]

                for w in wake_words:
                    if w in user_input:
                        user_input = user_input.replace(w, "")

                user_input = user_input.strip()

                if len(user_input.split()) < 1:
                    continue

                # =========================================
                # EXIT
                # =========================================
                if "exit" in user_input:
                    reset_audio()
                    speak("Going to sleep")
                    print("🔴 Voice mode OFF\n")
                    break

                # =========================================
                # INTENT
                # =========================================
                intent_data = intent_engine.detect_intent(user_input)
                print("🧠 DEBUG INTENT:", intent_data)

                # =========================================
                # ROUTER
                # =========================================
                response = route_command(user_input)

                logging.info(f"You (voice): {user_input}")
                logging.info(f"Intent: {intent_data}")
                logging.info(f"Jarvis: {response}")

                if response == "__EXIT__":
                    observer.stop()
                    observer.join()
                    reset_audio()
                    speak("Shutting down. Goodbye.")
                    exit()

                print("\nJarvis:", response, "\n")

                # =========================================
                # 🔊 SPEAK (FINAL FIX)
                # =========================================
                if isinstance(response, str):

                    
                    reset_audio()
                    time.sleep(0.25)

                    if "\n" in response:
                        lines = response.split("\n")
                        speak_lines = [line for line in lines if line.strip()][:3]
                        speak(" ".join(speak_lines))

                    elif len(response) < 200:
                        speak(response)

                    else:
                        short = " ".join(response.split("\n")[:2])
                        speak(short)

                last_activity = time.time()

            continue  # 🔥 back to wake mode

    except Exception as e:
        print("Voice error:", e)
        continue