"""
jarvis/memory/long_term.py
===========================
Long-term persistent memory with:
  - User identity (name, nicknames, preferences)
  - Important facts (permanent — never expire)
  - Episodic memory (auto-expire after 30 days)
"""

import os
import json
import logging
import time
from typing import Dict, Any, List, Optional


class LongTermMemory:
    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        self.logger       = logging.getLogger("Jarvis.LongTermMemory")
        self.pref_file    = os.path.join(storage_path, "preferences.json")
        self.facts_file   = os.path.join(storage_path, "facts.json")
        self.data:  Dict[str, Any]   = {}
        self.facts: List[Dict]       = []

        os.makedirs(self.storage_path, exist_ok=True)
        self.load()
        self._cleanup_expired_facts()

    # ── Load / Save ───────────────────────────────────────────────────────

    def load(self):
        """Load persistent user preferences and identity."""
        if os.path.exists(self.pref_file):
            try:
                with open(self.pref_file, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                self.logger.info("Loaded long-term preferences.")
            except Exception as e:
                self.logger.error(f"Failed to load preferences: {e}")
                self.data = {}
        else:
            self.data = {
                "user_name":         "User",
                "nicknames":         [],
                "preferences":       {},
                "habits":            {},
                "recurrent_workflows": {}
            }
            self.save()

        # Load facts
        if os.path.exists(self.facts_file):
            try:
                with open(self.facts_file, "r", encoding="utf-8") as f:
                    self.facts = json.load(f)
            except Exception:
                self.facts = []
        else:
            self.facts = []

    def save(self):
        """Save preferences to disk."""
        try:
            with open(self.pref_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Failed to save preferences: {e}")

    def _save_facts(self):
        try:
            with open(self.facts_file, "w", encoding="utf-8") as f:
                json.dump(self.facts, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Failed to save facts: {e}")

    # ── User identity ──────────────────────────────────────────────────────

    def get_user_name(self) -> str:
        return self.data.get("user_name", "User")

    def set_user_name(self, name: str):
        self.data["user_name"] = name
        self.save()
        self.logger.info(f"User name set to '{name}'")

    def get_nicknames(self) -> List[str]:
        return self.data.get("nicknames", [])

    def add_nickname(self, nick: str):
        nicks = self.data.setdefault("nicknames", [])
        if nick not in nicks:
            nicks.append(nick)
            self.save()

    def get_display_name(self) -> str:
        """Return the preferred name to use in conversation."""
        nicks = self.data.get("nicknames", [])
        return nicks[0] if nicks else self.data.get("user_name", "there")

    # ── Preferences ────────────────────────────────────────────────────────

    def get_preference(self, key: str, default: Any = None) -> Any:
        return self.data.get("preferences", {}).get(key, default)

    def set_preference(self, key: str, value: Any):
        self.data.setdefault("preferences", {})[key] = value
        self.save()

    # ── Facts memory ──────────────────────────────────────────────────────

    def remember_fact(self, fact: str, permanent: bool = False):
        """
        Store a fact about the user or world.
        permanent=True  → never expires (important facts)
        permanent=False → expires after 30 days (episodic/trash)
        """
        now    = time.time()
        expiry = None if permanent else now + 30 * 86400   # 30 days
        entry  = {
            "fact":      fact,
            "permanent": permanent,
            "created":   now,
            "expiry":    expiry,
        }
        # Avoid duplicates
        existing = [f["fact"] for f in self.facts]
        if fact not in existing:
            self.facts.append(entry)
            self._save_facts()
            kind = "permanent" if permanent else "30-day"
            self.logger.info(f"Memorised ({kind}): {fact!r}")

    def forget_fact(self, fact: str):
        """Remove a specific fact."""
        self.facts = [f for f in self.facts if f["fact"] != fact]
        self._save_facts()

    def get_all_facts(self) -> List[str]:
        """Return all currently valid facts as strings."""
        self._cleanup_expired_facts()
        return [f["fact"] for f in self.facts]

    def get_permanent_facts(self) -> List[str]:
        return [f["fact"] for f in self.facts if f.get("permanent")]

    def _cleanup_expired_facts(self):
        """Remove facts that have passed their expiry date."""
        now    = time.time()
        before = len(self.facts)
        self.facts = [
            f for f in self.facts
            if f.get("permanent") or f.get("expiry") is None or f["expiry"] > now
        ]
        removed = before - len(self.facts)
        if removed > 0:
            self._save_facts()
            self.logger.info(f"Cleaned up {removed} expired memory facts.")

    def facts_as_context(self) -> str:
        """Format all facts into a context string for LLM prompts."""
        facts = self.get_all_facts()
        if not facts:
            return ""
        return "Known facts about the user:\n" + "\n".join(f"- {f}" for f in facts)

    # ── Workflows ─────────────────────────────────────────────────────────

    def add_recurrent_workflow(self, trigger_phrase: str, plan_steps: list):
        self.data.setdefault("recurrent_workflows", {})[
            trigger_phrase.lower().strip()] = plan_steps
        self.save()
        self.logger.info(f"Learned workflow for: '{trigger_phrase}'")

    def get_workflow(self, trigger_phrase: str) -> Optional[list]:
        return self.data.get("recurrent_workflows", {}).get(
            trigger_phrase.lower().strip())

    def reset_memory(self):
        """Reset preferences and facts to default values and save to disk."""
        self.data = {
            "user_name":         "Kushal",
            "nicknames":         ["King"],
            "preferences":       {},
            "habits":            {},
            "recurrent_workflows": {}
        }
        self.facts = [
            {
                "fact": "User's name is Kushal, also known as King.",
                "permanent": True,
                "created": time.time(),
                "expiry": None
            },
            {
                "fact": "User prefers concise spoken answers, no bullet points.",
                "permanent": True,
                "created": time.time(),
                "expiry": None
            }
        ]
        self.save()
        self._save_facts()
        self.logger.info("Long-term memory has been reset to defaults.")

