from brain.router import route_command
from brain.voice import listen_for_wake, listen_continuous, speak

import logging
import os
from guardian.folder_monitor import start_folder_monitor
import guardian.folder_monitor as folder_monitor


# =====================================================
# SETUP LOGGING
# =====================================================
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    filename="logs/jarvis.log",
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
)


print("\nJarvis booting...")
print("Say 'Jarvis' to activate voice mode OR type commands.")
print("Type 'exit' to quit.\n")


# =====================================================
# START BACKGROUND FOLDER MONITOR
# =====================================================
observer = start_folder_monitor()


# =====================================================
# MAIN LOOP
# =====================================================
while True:

    # =================================================
    # 🚨 AUTO SECURITY TRIGGER (FILE BURST DETECTION)
    # =================================================
    if folder_monitor.burst_detected:
        print("\n🚨 Automatic Security Scan Triggered...\n")

        response = route_command("security scan")

        if response == "__EXIT__":
            observer.stop()
            observer.join()
            break

        print("\nJarvis:", response, "\n")

        # 🔥 ALWAYS SPEAK (no length restriction now)
        if isinstance(response, str):
            speak(response)

    # =================================================
    # 🎙 WAIT FOR WAKE WORD
    # =================================================
    try:
        print("🎙 Waiting for wake word OR manual input...")

        wake = listen_for_wake()

        # =================================================
        # 🎧 CONTINUOUS VOICE MODE (REAL JARVIS MODE)
        # =================================================
        if wake:
            while True:

                # 🔥 IMPORTANT:
                # listen_continuous() already STOPS mic internally before returning
                user_input = listen_continuous()

                # Exit only voice mode (not full system)
                if user_input == "__EXIT__":
                    print("🔴 Exiting voice mode...\n")
                    break

                # =================================================
                # 🧠 ROUTE COMMAND
                # =================================================
                response = route_command(user_input)

                logging.info(f"You (voice): {user_input}")
                logging.info(f"Jarvis: {response}")

                # =================================================
                # ❌ FULL SYSTEM EXIT
                # =================================================
                if response == "__EXIT__":
                    observer.stop()
                    observer.join()
                    speak("Shutting down. Goodbye.")
                    exit()

                # =================================================
                # 📤 PRINT RESPONSE
                # =================================================
                print("\nJarvis:", response, "\n")

                # =================================================
                # 🔥 CRITICAL FIX:
                # SPEAK AFTER MIC IS RELEASED
                # =================================================
                if isinstance(response, str):
                    speak(response)

    except Exception as e:
        print(f"⚠ Voice error: {e}")

    # =================================================
    # ⌨ MANUAL INPUT MODE (ALWAYS AVAILABLE)
    # =================================================
    user_input = input("You: ").strip()

    if not user_input:
        continue

    response = route_command(user_input)

    logging.info(f"You: {user_input}")
    logging.info(f"Jarvis: {response}")

    # =================================================
    # ❌ EXIT
    # =================================================
    if response == "__EXIT__":
        observer.stop()
        observer.join()
        speak("Shutting down. Goodbye.")
        break

    print("\nJarvis:", response, "\n")

    # 🔥 ALWAYS SPEAK
    if isinstance(response, str):
        speak(response)
