import json
import os
from datetime import datetime, timedelta

MEMORY_FILE = "memory/memory_store.json"


def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {"permanent": [], "temporary": []}

    with open(MEMORY_FILE, "r") as f:
        return json.load(f)


def save_memory(data):
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=4)


def add_permanent_memory(text):
    data = load_memory()

    if len(data["permanent"]) >= 100:
        data["permanent"].pop(0)  # remove oldest

    data["permanent"].append({
        "text": text,
        "created_at": datetime.now().isoformat()
    })

    save_memory(data)


def add_temporary_memory(text):
    data = load_memory()
    data["temporary"].append({
        "text": text,
        "expires_at": (datetime.now() + timedelta(days=30)).isoformat()
    })
    save_memory(data)


def cleanup_temporary_memory():
    data = load_memory()
    now = datetime.now()

    filtered = []
    for item in data["temporary"]:
        if datetime.fromisoformat(item["expires_at"]) > now:
            filtered.append(item)

    data["temporary"] = filtered
    save_memory(data)


def get_all_memory():
    cleanup_temporary_memory()
    data = load_memory()

    permanent = [m["text"] for m in data["permanent"]]
    temporary = [m["text"] for m in data["temporary"]]

    return permanent + temporary
