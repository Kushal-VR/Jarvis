import re

# =====================================================
# COMMAND CATEGORIES
# =====================================================

SAFE_COMMANDS = [
    "hello",
    "hi",
    "what",
    "who",
    "tell",
    "explain",
    "open",
    "search",
]

SENSITIVE_COMMANDS = [
    "delete",
    "remove",
    "terminate",
    "kill",
    "shutdown",
    "format",
    "reset",
]

CRITICAL_PATTERNS = [
    "delete all",
    "remove all",
    "wipe",
    "format disk",
    "rm -rf",
    "del /s",
]

INJECTION_PATTERNS = [
    "ignore previous instructions",
    "act as system",
    "disable safety",
    "bypass security",
    "you are not chatgpt",
    "execute without permission",
]


# =====================================================
# COMMAND CLASSIFIER
# =====================================================
def classify_command(text: str):
    lower = text.lower()

    for pattern in CRITICAL_PATTERNS:
        if pattern in lower:
            return "CRITICAL"

    for pattern in INJECTION_PATTERNS:
        if pattern in lower:
            return "INJECTION"

    for word in SENSITIVE_COMMANDS:
        if word in lower:
            return "SENSITIVE"

    return "SAFE"


# =====================================================
# SMART DECISION ENGINE
# =====================================================
def check_injection(user_input: str):
    text = user_input.lower()

    category = classify_command(text)

    # -------------------------
    # CRITICAL → HARD BLOCK
    # -------------------------
    if category == "CRITICAL":
        return "BLOCK", "Critical destructive command detected"

    # -------------------------
    # INJECTION → HARD BLOCK
    # -------------------------
    if category == "INJECTION":
        return "BLOCK", "Prompt injection attempt detected"

    # -------------------------
    # SENSITIVE → CONTEXT CHECK
    # -------------------------
    if category == "SENSITIVE":

        # Example: "delete temp file" → safer
        if "temp" in text or "cache" in text:
            return "WARN", "Low-risk cleanup command detected"

        # Example: specific file/process
        if re.search(r"\b(delete|terminate|remove)\s+\w+", text):
            return "WARN", "Sensitive command detected"

        return "WARN", "Unverified sensitive command"

    # -------------------------
    # SAFE → ALLOW
    # -------------------------
    return "ALLOW", "Safe command"
