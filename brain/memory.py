import json
import os
from datetime import datetime, timedelta

# =====================================================
# MEMORY FILE LOCATION
# =====================================================
MEMORY_FILE = "memory/memory_store.json"


# =====================================================
# LOAD MEMORY SAFELY
# Ensures required sections always exist
# =====================================================
def load_memory():

    if not os.path.exists(MEMORY_FILE):
        return {
            "permanent": [],
            "temporary": [],
            "security_events": []
        }

    with open(MEMORY_FILE, "r") as f:
        data = json.load(f)

    # Backward compatibility (important)
    if "permanent" not in data:
        data["permanent"] = []

    if "temporary" not in data:
        data["temporary"] = []

    if "security_events" not in data:
        data["security_events"] = []

    return data


# =====================================================
# SAVE MEMORY
# =====================================================
def save_memory(data):
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=4)


# =====================================================
# PERMANENT MEMORY
# Only stored when explicitly requested
# =====================================================
def add_permanent_memory(text):

    data = load_memory()

    # Keep max 100 permanent memories
    if len(data["permanent"]) >= 100:
        data["permanent"].pop(0)

    data["permanent"].append({
        "text": text,
        "created_at": datetime.now().isoformat()
    })

    save_memory(data)

    return "Memory stored permanently."


# =====================================================
# TEMPORARY MEMORY (AUTO EXPIRE — 30 DAYS)
# =====================================================
def add_temporary_memory(text):

    data = load_memory()

    data["temporary"].append({
        "text": text,
        "expires_at": (
            datetime.now() + timedelta(days=30)
        ).isoformat()
    })

    save_memory(data)

    return "Temporary memory stored for 30 days."


# =====================================================
# TEMPORARY MEMORY CLEANUP
# Runs automatically during recall
# =====================================================
def cleanup_temporary_memory():

    data = load_memory()
    now = datetime.now()

    filtered = []

    for item in data["temporary"]:
        try:
            expiry = datetime.fromisoformat(item["expires_at"])
            if expiry > now:
                filtered.append(item)
        except:
            continue

    data["temporary"] = filtered
    save_memory(data)

# =====================================================
# CLEAR TEMPORARY MEMORY
# =====================================================

def clear_temporary_memory():
    global temporary_memory
    temporary_memory = []
    return "Temporary memory cleared."

# =====================================================
# SECURITY MEMORY (NEW)
# Guardian can store security events here
# =====================================================
def add_security_event(event_text):

    data = load_memory()

    data["security_events"].append({
        "event": event_text,
        "time": datetime.now().isoformat()
    })

    save_memory(data)


# =====================================================
# MEMORY RECALL
# Returns readable memory list
# =====================================================
def get_all_memory():

    cleanup_temporary_memory()

    data = load_memory()

    output = []

    if data["permanent"]:
        output.append("Permanent memories:")
        for m in data["permanent"][-10:]:
            output.append(f" - {m['text']}")

    if data["temporary"]:
        output.append("\nTemporary memories:")
        for m in data["temporary"][-10:]:
            output.append(f" - {m['text']}")

    if not output:
        return "I do not have any stored memories yet."

    return "\n".join(output)
