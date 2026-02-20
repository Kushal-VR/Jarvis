from brain.router import route_command
from brain.voice import listen_for_wake, speak
from brain.whisper_engine import transcribe_audio

import logging
import os
from guardian.folder_monitor import start_folder_monitor
import guardian.folder_monitor as folder_monitor


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

    # 🚨 AUTO SECURITY
    if folder_monitor.burst_detected:
        print("\n🚨 Automatic Security Scan Triggered...\n")

        response = route_command("security scan")

        print("\nJarvis:", response, "\n")

        if isinstance(response, str):
            speak(response)

    # =========================================
    # 🎙 WAIT FOR WAKE WORD
    # =========================================
    try:
        print("🎙 Waiting for wake word...")
        wake = listen_for_wake()

        # =========================================
        # 🔥 CONTINUOUS VOICE MODE (FIXED)
        # =========================================
        if wake:
            speak("Listening")

            while True:
                print("🎧 Listening (Whisper)...")

                user_input = transcribe_audio()
                
                # 🔥 IGNORE GARBAGE / LOW QUALITY TEXT
                if user_input:
                  words = user_input.split()

                 # too short
                  # allow single-word commands like exit
                if len(words) < 2 and user_input.lower() not in ["exit", "stop"]:
                  print("⚠ Ignored noise")
                  continue

                 # too weird (non-english heavy)
                strange_chars = sum(1 for c in user_input if not c.isalnum() and c != " ")
                if strange_chars > len(user_input) * 0.3:
                    print("⚠ Ignored garbage input")
                    continue
                
                # 🔥 HANDLE SILENCE / FAIL
                if not user_input or user_input.strip() == "":
                    print("⚠ No voice detected, retrying...")
                    continue

            

                # 🔥 EXIT VOICE MODE ONLY
                if "exit" in user_input.lower():
                    speak("Exiting voice mode")
                    print("🔴 Voice mode OFF\n")
                    break

                # =========================================
                # 🧠 ROUTER
                # =========================================
                response = route_command(user_input)

                logging.info(f"You (voice): {user_input}")
                logging.info(f"Jarvis: {response}")

                if response == "__EXIT__":
                    observer.stop()
                    observer.join()
                    speak("Shutting down. Goodbye.")
                    exit()

                print("\nJarvis:", response, "\n")

                if isinstance(response, str):
                    speak(response)

    except Exception as e:
        print("Voice error:", e)

    # =========================================
    # ⌨ FALLBACK MODE (ONLY IF USER TYPES)
    # =========================================
    user_input = input("You: ").strip()

    if not user_input:
        continue

    response = route_command(user_input)

    logging.info(f"You: {user_input}")
    logging.info(f"Jarvis: {response}")

    if response == "__EXIT__":
        observer.stop()
        observer.join()
        speak("Shutting down. Goodbye.")
        break

    print("\nJarvis:", response, "\n")

    if isinstance(response, str):
        speak(response)