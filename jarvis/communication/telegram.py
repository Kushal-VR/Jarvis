import requests
import logging
from typing import Dict, Any, List

class TelegramNotifier:
    def __init__(self, bot_token: str, default_chat_id: str = None):
        self.bot_token = bot_token
        self.default_chat_id = default_chat_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.logger = logging.getLogger("Jarvis.Telegram")

    def send_message(self, message: str, chat_id: str = None) -> bool:
        """Sends a notification to a Telegram chat."""
        target_chat = chat_id or self.default_chat_id
        if not target_chat:
            self.logger.error("No Telegram chat ID provided.")
            return False

        self.logger.info(f"Sending Telegram notification to {target_chat}...")
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": target_chat,
            "text": message,
            "parse_mode": "HTML"
        }

        try:
            res = requests.post(url, json=payload, timeout=10)
            res.raise_for_status()
            self.logger.info("Telegram notification sent successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to send Telegram notification: {e}")
            return False

    def fetch_updates(self) -> List[Dict[str, Any]]:
        """Fetches recent incoming messages to the bot."""
        url = f"{self.base_url}/getUpdates"
        try:
            res = requests.get(url, timeout=10)
            res.raise_for_status()
            updates = res.json().get("result", [])
            messages = []
            for update in updates:
                msg = update.get("message", {})
                if msg:
                    messages.append({
                        "chat_id": msg.get("chat", {}).get("id"),
                        "username": msg.get("from", {}).get("username"),
                        "text": msg.get("text", "")
                    })
            return messages
        except Exception as e:
            self.logger.error(f"Failed to fetch Telegram updates: {e}")
            return []
