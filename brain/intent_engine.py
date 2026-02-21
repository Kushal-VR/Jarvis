# brain/intent_engine.py

"""
Intent Engine

This module converts raw user input into structured intent.
It acts as the brain's understanding layer.

Example:
Input: "search latest AI news"
Output:
{
    "intent": "search_web",
    "entities": {"query": "latest AI news"}
}
"""

import re


class IntentEngine:

    def __init__(self):
        """
        Define regex patterns for different intents.
        You can expand this later.
        """

        self.patterns = {
            "open_app": r"open (.+)",
            "shutdown": r"(shutdown|turn off)",
            "restart": r"(restart)",
            "search_web": r"(search|find|look up) (.+)",
            "read_file": r"(read|open file) (.+)",
            "send_message": r"(send message|send) (.+)",
        }

    def detect_intent(self, text: str) -> dict:
        """
        Convert user text into structured intent.
        """

        # Normalize text
        text = text.lower().strip()

        # Try matching patterns
        for intent, pattern in self.patterns.items():
            match = re.search(pattern, text)

            if match:
                return self._build_intent(intent, match)
        # =========================================
        # 🔥 SMART SEARCH DETECTION (IMPORTANT)
        # =========================================
        search_keywords = ["news", "latest", "update", "updates", "happening", "recent"]

        if any(word in text for word in search_keywords):
           return {
              "intent": "search_web",
              "entities": {"query": text}
         }
        # Fallback
        return {
            "intent": "general_query",
            "entities": {"text": text}
        }

    # =====================================================
    # 🔥 NEW: CLEAN ENTITY TEXT
    # =====================================================
    def _clean_text(self, text: str) -> str:
       """
        Smart cleaning:
        - Keeps valid dots (main.py)
        - Removes trailing punctuation
        - Removes filler words
       """

       text = text.lower().strip()

       # remove filler words
       remove_words = ["file", "please", "jarvis"]

       words = text.split()
       words = [w for w in words if w not in remove_words]

       text = " ".join(words)

       # remove ONLY trailing punctuation (not inside)
       text = text.rstrip(".,!?")

       return text.strip()

    # =====================================================
    # 🔥 UPDATED: BUILD INTENT (WITH CLEANING)
    # =====================================================
    def _build_intent(self, intent, match):
        """
        Extract and clean entities based on intent
        """

        # Web search → clean query
        if intent == "search_web":
            query = self._clean_text(match.group(2))

            return {
                "intent": intent,
                "entities": {"query": query}
            }

        # Open app → clean app name
        if intent == "open_app":
            app = self._clean_text(match.group(1))

            return {
                "intent": intent,
                "entities": {"app": app}
            }

        # Read file → clean filename
        if intent == "read_file":
            file = self._clean_text(match.group(2))

            return {
                "intent": intent,
                "entities": {"file": file}
            }

        # Default case
        return {
            "intent": intent,
            "entities": {}
        }