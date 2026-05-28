import logging
from typing import List, Dict, Any

class ShortTermMemory:
    def __init__(self, max_turns: int = 15):
        self.max_turns = max_turns
        self.history: List[Dict[str, str]] = []
        self.active_variables: Dict[str, Any] = {}
        self.logger = logging.getLogger("Jarvis.ShortTermMemory")

    def add_message(self, role: str, content: str):
        """Appends a dialogue turn to conversation memory."""
        self.history.append({"role": role, "content": content})
        # Prune conversation history to fit max context window
        if len(self.history) > self.max_turns * 2:
            self.history = self.history[-self.max_turns * 2:]
        self.logger.debug(f"Added message to history. Current history size: {len(self.history)}")

    def get_context_messages(self) -> List[Dict[str, str]]:
        return self.history

    def get_variable(self, key: str, default: Any = None) -> Any:
        return self.active_variables.get(key, default)

    def set_variable(self, key: str, value: Any):
        self.active_variables[key] = value

    def clear(self):
        self.history.clear()
        self.active_variables.clear()
        self.logger.info("Short-term conversation memory cleared.")
