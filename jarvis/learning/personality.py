"""
jarvis/learning/personality.py
================================
Personality & Learning Engine — Jarvis gradually learns the user.

Tracks:
  - Communication style (slang, shortcuts, vocabulary)
  - Mood estimation from text patterns
  - Contextual awareness (recent apps, topics, files)
  - Habit patterns (time-of-day behaviors)
  - Command synonyms (learns that "bro chrome" = "open chrome")
  - Skill level per topic
  - Response preferences

All data is stored locally in JSON. Nothing sent externally.
"""

import os
import json
import time
import math
import re
import logging
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from typing import Dict, List, Optional, Tuple, Any


class PersonalityEngine:
    # ── Mood keyword maps ─────────────────────────────────────────────────
    MOOD_SIGNALS = {
        "stressed":   ["asap", "urgent", "hurry", "quick", "deadline",
                       "ugh", "shit", "fuck", "damn", "help me", "need this now",
                       "not working", "broken", "why won't", "again"],
        "frustrated": ["again", "still", "still not", "why", "stop", "enough",
                       "for the last time", "i said", "wrong", "incorrect",
                       "that's wrong", "no no"],
        "excited":    ["wow", "amazing", "awesome", "great", "yes!", "yess",
                       "let's go", "nice", "perfect", "love it", "sick"],
        "tired":      ["tired", "sleepy", "bored", "boring", "slow", "zzz",
                       "whatever", "don't care", "fine", "ok ok"],
        "curious":    ["how", "why", "what if", "explain", "tell me more",
                       "interesting", "i wonder", "can you", "is it possible"],
        "focused":    [],   # Short precise commands with no filler
        "calm":       [],   # Default
    }

    # Slang → standard mapping seeds
    SLANG_MAP = {
        "bro":     "",      # filler, ignore
        "yo":      "",
        "bruh":    "",
        "lemme":   "let me",
        "gonna":   "going to",
        "wanna":   "want to",
        "gotta":   "got to",
        "kinda":   "kind of",
        "ngl":     "not gonna lie",
        "tbh":     "to be honest",
        "rn":      "right now",
        "ig":      "i guess",
        "idk":     "i don't know",
        "asap":    "as soon as possible",
        "lmk":     "let me know",
        "fyi":     "for your information",
    }

    # ── Init ──────────────────────────────────────────────────────────────

    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        self.logger = logging.getLogger("Jarvis.Personality")
        os.makedirs(storage_path, exist_ok=True)

        self._vocab_file    = os.path.join(storage_path, "vocab.json")
        self._synonyms_file = os.path.join(storage_path, "synonyms.json")
        self._habits_file   = os.path.join(storage_path, "habits.json")
        self._context_file  = os.path.join(storage_path, "context.json")
        self._mood_file     = os.path.join(storage_path, "mood_log.json")
        self._skills_file   = os.path.join(storage_path, "skills.json")

        self._load_all()

        # In-session state
        self._current_mood    = "calm"
        self._mood_history    = []          # last 10 mood readings
        self._session_context = {}          # things mentioned this session
        self._last_response   = ""          # for "say that again"
        self._conversation    = []          # last 10 (user, jarvis) pairs

    # ── Load / Save ───────────────────────────────────────────────────────

    def _load_all(self):
        self.vocab     = self._load_json(self._vocab_file,    {})
        self.synonyms  = self._load_json(self._synonyms_file, {})
        self.habits    = self._load_json(self._habits_file,   {})
        self.context   = self._load_json(self._context_file,  {
            "last_app": None, "last_file": None, "last_topic": None,
            "recent_apps": [], "recent_files": [], "recent_people": []
        })
        self.mood_log  = self._load_json(self._mood_file,    [])
        self.skills    = self._load_json(self._skills_file,  {})

    def _load_json(self, path: str, default: Any) -> Any:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return default

    def _save_json(self, path: str, data: Any):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Save failed ({path}): {e}")

    def save_all(self):
        self._save_json(self._vocab_file,    self.vocab)
        self._save_json(self._synonyms_file, self.synonyms)
        self._save_json(self._habits_file,   self.habits)
        self._save_json(self._context_file,  self.context)
        self._save_json(self._mood_file,     self.mood_log[-200:])  # keep last 200
        self._save_json(self._skills_file,   self.skills)

    # ── Main analysis entry point ─────────────────────────────────────────

    def analyze(self, user_text: str) -> Dict:
        """
        Full analysis of a user utterance.
        Returns a dict with: mood, style, context, normalized_text, topics
        """
        mood           = self._estimate_mood(user_text)
        normalized     = self._normalize_text(user_text)
        topics         = self._extract_topics(normalized)
        style          = self._get_response_style(mood, user_text)

        # Update running state
        self._current_mood = mood
        self._mood_history = (self._mood_history + [mood])[-10:]
        self._update_vocab(user_text)
        self._update_context(normalized, topics)
        self._update_habits(user_text)

        return {
            "mood":             mood,
            "normalized":       normalized,
            "topics":           topics,
            "response_style":   style,
            "dominant_mood":    self._dominant_mood(),
        }

    def record_exchange(self, user_text: str, jarvis_text: str):
        """Remember what was just said for context + 'say that again'."""
        self._last_response = jarvis_text
        self._conversation  = (self._conversation + [(user_text, jarvis_text)])[-10:]

    def get_last_response(self) -> str:
        return self._last_response

    # ── Mood estimation ───────────────────────────────────────────────────

    def _estimate_mood(self, text: str) -> str:
        t = text.lower()
        scores: Dict[str, float] = defaultdict(float)

        for mood, keywords in self.MOOD_SIGNALS.items():
            for kw in keywords:
                if kw in t:
                    scores[mood] += 1.0

        # Punctuation signals
        if text.count("!") >= 2:
            scores["excited"] += 0.5
        if text.count("?") >= 2:
            scores["curious"] += 0.5
        words = text.split()
        if len(words) <= 3 and not scores:
            scores["focused"] += 1.0   # very short command

        if not scores:
            return "calm"
        return max(scores, key=lambda k: scores[k])

    def _dominant_mood(self) -> str:
        if not self._mood_history:
            return "calm"
        return Counter(self._mood_history).most_common(1)[0][0]

    # ── Response style ────────────────────────────────────────────────────

    def _get_response_style(self, mood: str, user_text: str) -> Dict:
        """
        Return LLM prompt parameters based on detected mood.
        """
        base = {"max_sentences": 2, "tone": "helpful", "detail": "medium"}

        if mood == "stressed":
            return {**base, "max_sentences": 1, "tone": "calm and concise",
                    "detail": "minimal"}
        elif mood == "frustrated":
            return {**base, "max_sentences": 1, "tone": "apologetic and direct",
                    "detail": "minimal"}
        elif mood == "excited":
            return {**base, "max_sentences": 2, "tone": "enthusiastic",
                    "detail": "medium"}
        elif mood == "curious":
            return {**base, "max_sentences": 3, "tone": "informative",
                    "detail": "detailed"}
        elif mood == "tired":
            return {**base, "max_sentences": 1, "tone": "gentle",
                    "detail": "minimal"}
        elif mood == "focused":
            return {**base, "max_sentences": 1, "tone": "direct",
                    "detail": "minimal"}
        return base

    # ── Text normalization ────────────────────────────────────────────────

    def _normalize_text(self, text: str) -> str:
        """Replace slang, user-learned shortcuts with standard text."""
        words = text.lower().split()
        out   = []
        for w in words:
            clean = re.sub(r"[^\w]", "", w)
            if clean in self.SLANG_MAP:
                replacement = self.SLANG_MAP[clean]
                if replacement:
                    out.append(replacement)
                # else: skip filler words like "bro", "yo"
            elif clean in self.synonyms:
                out.append(self.synonyms[clean])
            else:
                out.append(w)
        return " ".join(out)

    # ── Vocabulary learning ───────────────────────────────────────────────

    def _update_vocab(self, text: str):
        words = re.findall(r"\b\w+\b", text.lower())
        for w in words:
            self.vocab[w] = self.vocab.get(w, 0) + 1

    def get_top_words(self, n: int = 20) -> List[Tuple[str, int]]:
        """Most frequently used words by the user."""
        stop = {"the","a","an","is","it","to","and","of","in","that",
                "i","you","me","my","we","on","at","do","for","jarvis"}
        filtered = {k: v for k, v in self.vocab.items() if k not in stop and len(k) > 2}
        return sorted(filtered.items(), key=lambda x: -x[1])[:n]

    # ── Synonym / shortcut learning ───────────────────────────────────────

    def learn_synonym(self, user_phrase: str, canonical_action: str):
        """
        Learn that user_phrase maps to canonical_action.
        E.g. learn_synonym("bro chrome", "open chrome")
        """
        key = user_phrase.lower().strip()
        self.synonyms[key] = canonical_action
        self.logger.info(f"Learned synonym: '{key}' -> '{canonical_action}'")
        self._save_json(self._synonyms_file, self.synonyms)

    def resolve_synonyms(self, text: str) -> str:
        """Attempt to map full user utterance to a known canonical command."""
        t = text.lower().strip()
        if t in self.synonyms:
            return self.synonyms[t]
        # Partial match
        for phrase, canonical in self.synonyms.items():
            if phrase in t:
                return canonical
        return text

    # ── Topic / context extraction ────────────────────────────────────────

    TOPIC_KEYWORDS = {
        "cricket":  ["ipl", "cricket", "match", "score", "wicket", "batting", "bowling"],
        "weather":  ["weather", "rain", "sunny", "temperature", "forecast", "humidity"],
        "coding":   ["code", "python", "debug", "error", "script", "function", "api"],
        "music":    ["music", "song", "play", "spotify", "youtube", "track", "album"],
        "news":     ["news", "today", "latest", "current", "happening", "update"],
        "finance":  ["stock", "price", "market", "bitcoin", "crypto", "money"],
        "health":   ["health", "medicine", "doctor", "exercise", "diet", "sleep"],
        "sports":   ["sports", "football", "tennis", "basketball", "game"],
    }

    def _extract_topics(self, text: str) -> List[str]:
        t = text.lower()
        found = []
        for topic, keywords in self.TOPIC_KEYWORDS.items():
            if any(kw in t for kw in keywords):
                found.append(topic)
        return found

    def _update_context(self, text: str, topics: List[str]):
        """Update running context with what the user just mentioned."""
        if topics:
            self.context["last_topic"] = topics[0]

        # Extract app names
        app_patterns = r"\b(chrome|firefox|edge|spotify|notepad|excel|word|vs ?code|terminal|discord|teams)\b"
        apps = re.findall(app_patterns, text.lower())
        if apps:
            self.context["last_app"] = apps[0]
            recent = self.context.get("recent_apps", [])
            if apps[0] not in recent:
                self.context["recent_apps"] = (recent + [apps[0]])[-10:]

        # Save periodically
        self._save_json(self._context_file, self.context)

    def get_context_summary(self) -> str:
        """Build a short context string for LLM prompts."""
        parts = []
        if self.context.get("last_app"):
            parts.append(f"recently used app: {self.context['last_app']}")
        if self.context.get("last_topic"):
            parts.append(f"recent topic: {self.context['last_topic']}")
        if self.context.get("last_file"):
            parts.append(f"recent file: {self.context['last_file']}")
        return "; ".join(parts) if parts else ""

    # ── Habit tracking ────────────────────────────────────────────────────

    def _update_habits(self, text: str):
        """Record what user does at what hour of the day."""
        hour = datetime.now().hour
        key  = str(hour)
        entry = self.habits.get(key, [])
        words = text.lower().split()[:3]   # first 3 words as action signature
        entry.append(" ".join(words))
        self.habits[key] = entry[-20:]     # keep last 20 per hour
        self._save_json(self._habits_file, self.habits)

    def predict_next_action(self) -> Optional[str]:
        """Based on time-of-day habits, suggest what user might want."""
        hour = str(datetime.now().hour)
        if hour not in self.habits:
            return None
        actions = Counter(self.habits[hour])
        if not actions:
            return None
        top = actions.most_common(1)[0]
        if top[1] >= 3:     # only suggest if seen 3+ times
            return top[0]
        return None

    # ── Skill level ───────────────────────────────────────────────────────

    SKILL_TOPICS = {
        "coding":  ["code", "python", "function", "class", "bug", "debug",
                    "import", "variable", "loop", "api", "git"],
        "linux":   ["linux", "bash", "terminal", "sudo", "chmod", "grep"],
        "finance": ["stock", "portfolio", "dividend", "crypto", "trading"],
    }

    def update_skill_level(self, text: str):
        """Estimate skill level from vocabulary complexity."""
        t = text.lower()
        for domain, keywords in self.SKILL_TOPICS.items():
            matches = sum(1 for kw in keywords if kw in t)
            if matches > 0:
                current = self.skills.get(domain, 0)
                # Slowly increase level (0–100)
                self.skills[domain] = min(100, current + matches * 2)
        self._save_json(self._skills_file, self.skills)

    def get_skill_level(self, domain: str) -> str:
        score = self.skills.get(domain, 0)
        if score < 20:   return "beginner"
        if score < 60:   return "intermediate"
        return "advanced"

    # ── Prompt enrichment ─────────────────────────────────────────────────

    def build_system_prompt(self, user_name: str, analysis: Dict) -> str:
        """
        Build a rich system prompt that personalizes the LLM response.
        """
        mood     = analysis.get("mood", "calm")
        style    = analysis.get("response_style", {})
        ctx      = self.get_context_summary()
        max_sent = style.get("max_sentences", 2)
        tone     = style.get("tone", "helpful")

        mood_instruction = {
            "stressed":   "The user seems stressed. Be very brief and calm.",
            "frustrated": "The user seems frustrated. Apologize if needed, be direct.",
            "excited":    "The user is excited. Match their energy.",
            "curious":    "The user is curious. Provide a helpful explanation.",
            "tired":      "The user seems tired. Keep it very short and gentle.",
            "focused":    "The user is focused. Give a concise direct answer.",
            "calm":       "Respond naturally.",
        }.get(mood, "Respond naturally.")

        context_str = f" Context: {ctx}." if ctx else ""

        return (
            f"You are Jarvis, an intelligent AI assistant. "
            f"Address the user as {user_name}. "
            f"{mood_instruction}"
            f"{context_str} "
            f"Reply in {max_sent} sentence(s) max. "
            f"Tone: {tone}. "
            f"No markdown, no lists, no bullet points. Spoken sentences only."
        )

    # ── Persistence helper ────────────────────────────────────────────────

    def get_summary_for_display(self) -> str:
        """Human-readable summary of what Jarvis has learned."""
        top_words = self.get_top_words(5)
        word_str  = ", ".join(f"{w}({c})" for w, c in top_words)
        skills    = ", ".join(f"{d}:{self.get_skill_level(d)}"
                              for d in self.skills if self.skills[d] > 0)
        mood      = self._dominant_mood()
        ctx       = self.context.get("last_topic", "nothing yet")
        return (
            f"Mood: {mood} | Last topic: {ctx} | "
            f"Top words: {word_str} | Skills: {skills or 'learning...'}"
        )

    def reset_memory(self):
        """Wipes vocabulary, synonyms, habits, context, mood log, and skills."""
        self.vocab = {}
        self.synonyms = {}
        self.habits = {}
        self.context = {
            "last_app": None,
            "last_file": None,
            "last_topic": None,
            "recent_apps": [],
            "recent_files": [],
            "recent_people": []
        }
        self.mood_log = []
        self.skills = {}
        self.save_all()
        
        # Reset session states
        self._current_mood = "calm"
        self._mood_history = []
        self._session_context = {}
        self._last_response = ""
        self._conversation = []
        self.logger.info("Personality engine memory has been reset.")

