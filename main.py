from brain.router import route_command
from brain.voice import listen_for_wake, speak
from brain.whisper_engine import transcribe_audio
from brain.intent_engine import IntentEngine  # ✅ NEW
from brain.command_normalizer import normalize_command  # ✅ NEW
import logging
import os
from guardian.folder_monitor import start_folder_monitor
import guardian.folder_monitor as folder_monitor


# =========================================
# INIT INTENT ENGINE
# =========================================
intent_engine = IntentEngine()  # ✅ NEW


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
        # 🔥 CONTINUOUS VOICE MODE
        # =========================================
        if wake:
            speak("Listening")

            while True:
                print("🎧 Listening (Whisper)...")

                user_input = transcribe_audio()

                # 🔥 NORMALIZE VOICE INPUT
                if user_input:
                    user_input = normalize_command(user_input)
                    print("🧹 NORMALIZED:", user_input)

                # 🔥 HANDLE SILENCE
                if not user_input or user_input.strip() == "":
                    print("⚠ No voice detected, retrying...")
                    continue

                words = user_input.lower().split()

                # 🔥 IGNORE GARBAGE
                if len(words) < 2 and user_input.lower() not in ["exit", "stop"]:
                    print("⚠ Ignored noise")
                    continue

                # 🔥 FILTER WEIRD INPUT
                strange_chars = sum(1 for c in user_input if not c.isalnum() and c != " ")
                if strange_chars > len(user_input) * 0.3:
                    print("⚠ Ignored garbage input")
                    continue

                # 🔥 EXIT VOICE MODE
                if "exit" in user_input.lower():
                    speak("Exiting voice mode")
                    print("🔴 Voice mode OFF\n")
                    break
                
                # reject repetitive garbage
                if len(set(words)) < len(words) * 0.3:
                    print("⚠ Repetitive noise ignored")
                    continue
                # =========================================
                # 🧠 INTENT ENGINE (NEW)
                # =========================================
                intent_data = intent_engine.detect_intent(user_input)

                print("🧠 DEBUG INTENT:", intent_data)  # ✅ DEBUG

                # =========================================
                # 🧠 ROUTER (UNCHANGED)
                # =========================================
                response = route_command(user_input)

                logging.info(f"You (voice): {user_input}")
                logging.info(f"Intent: {intent_data}")  # ✅ NEW LOG
                logging.info(f"Jarvis: {response}")

                if response == "__EXIT__":
                    observer.stop()
                    observer.join()
                    speak("Shutting down. Goodbye.")
                    exit()

                print("\nJarvis:", response, "\n")

                if isinstance(response, str):

                    # 🔥 If it's structured (like news / list), speak first few lines
                    if "\n" in response:
                        lines = response.split("\n")

                        # speak only first 3 meaningful lines
                        speak_lines = [line for line in lines if line.strip()][:4]

                        speak(" ".join(speak_lines))

                    elif len(response) < 300:
                        speak(response)

                    else:
                        # speak only summary (clean)
                        lines = response.split("\n")

                        short = " ".join(lines[:2])  # only first 2 lines
                        speak(short)
   
    except Exception as e:
        print("Voice error:", e)

    # =========================================
    # ⌨ FALLBACK MODE
    # =========================================
    user_input = input("You: ").strip()

    if user_input:
      user_input = normalize_command(user_input)
    
    if not user_input:
        continue

    # =========================================
    # 🧠 INTENT ENGINE (NEW)
    # =========================================
    intent_data = intent_engine.detect_intent(user_input)

    print("🧠 DEBUG INTENT:", intent_data)  # ✅ DEBUG

    response = route_command(user_input)

    logging.info(f"You: {user_input}")
    logging.info(f"Intent: {intent_data}")  # ✅ NEW LOG
    logging.info(f"Jarvis: {response}")

    if response == "__EXIT__":
        observer.stop()
        observer.join()
        speak("Shutting down. Goodbye.")
        break

    print("\nJarvis:", response, "\n")

    if isinstance(response, str):
        speak(response)