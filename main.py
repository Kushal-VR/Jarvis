from brain.router import route_command
import logging
import os

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    filename="logs/jarvis.log",
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
)

print("\nJarvis booting...\nType 'exit' to quit.\n")

while True:
    user = input("You: ").strip()

    if not user:
        continue

    logging.info(f"USER: {user}")

    reply = route_command(user)

    if reply == "__EXIT__":
        break

    logging.info(f"JARVIS: {reply}")

    print("\nJarvis:", reply, "\n")
