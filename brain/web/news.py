# brain/web/news.py

"""
Robust News Engine (FINAL FIX)
"""

import feedparser
import re


def clean_text(text):
    """
    Remove weird characters and noise
    """
    text = text.strip()

    # remove non-readable characters
    text = re.sub(r"[^\w\s.,:-]", "", text)

    return text


def get_ai_news():
    url = "https://news.google.com/rss/search?q=AI&hl=en-IN&gl=IN&ceid=IN:en"

    feed = feedparser.parse(url)

    results = []

    for entry in feed.entries:

        title = entry.get("title", "")

        title = clean_text(title)

        # 🔥 STRONG FILTER
        if (
            not title
            or len(title) < 15
            or title.isdigit()
            or title.lower() in ["...", "-", "|"]
        ):
            continue

        results.append(title)

        if len(results) >= 5:
            break

    return results