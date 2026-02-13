from brain.router import route_command
import logging
import os
from guardian.folder_monitor import start_folder_monitor
import guardian.folder_monitor as folder_monitor

# -----------------------------------------
# Setup logging directory
# -----------------------------------------
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    filename="logs/jarvis.log",
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
)

print("\nJarvis booting...\nType 'exit' to quit.\n")

# -----------------------------------------
# Start background folder monitor
# -----------------------------------------
observer = start_folder_monitor()

# -----------------------------------------
# Main Event Loop
# -----------------------------------------
while True:

    # -----------------------------------------
    # AUTO SECURITY TRIGGER (File Burst)
    # -----------------------------------------
    if folder_monitor.burst_detected:
        print("\n🚨 Automatic Security Scan Triggered...\n")

        # DO NOT reset here.
        # get_folder_risk() inside scan_system() will reset properly.

        response = route_command("security scan")

        if response == "__EXIT__":
            observer.stop()
            observer.join()
            break

        print("\nJarvis:", response, "\n")

    # -----------------------------------------
    # User Input
    # -----------------------------------------
    user = input("You: ").strip()

    if not user:
        continue

    response = route_command(user)

    if response == "__EXIT__":
        observer.stop()
        observer.join()
        break

    print("\nJarvis:", response, "\n")
