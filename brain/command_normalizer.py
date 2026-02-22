# brain/command_normalizer.py

"""
Command Normalizer

Fixes noisy voice input:
- "dot" → "."
- removes filler words
- fixes broken filenames
"""

import re


def normalize_command(text: str) -> str:
    """
    Cleans and fixes voice input before intent detection
    """

    text = text.lower().strip()

    # =========================================
    # FIX COMMON VOICE PATTERNS
    # =========================================

    # "dot" → "."
    text = text.replace(" dot ", ".")

    # fix cases like "main dot py"
    text = re.sub(r"\b(\w+)\s+dot\s+(\w+)\b", r"\1.\2", text)

    # fix extensions like "p y" → "py"
    text = re.sub(r"\b(p y)\b", "py", text)
    text = re.sub(r"\b(j s)\b", "js", text)

    # =========================================
    # REMOVE FILLER WORDS
    # =========================================
    fillers = ["please", "hey", "i said", "can you", "just"]

    for f in fillers:
        text = text.replace(f, "")

    # =========================================
    # CLEAN EXTRA SPACES
    # =========================================
    text = " ".join(text.split())

    return text.strip()