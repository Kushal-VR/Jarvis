# =====================================================
# ROUTER - EXECUTION LAYER (FINAL UPGRADED)
# =====================================================

from brain.llm import ask_llm
from brain.orchestrator import orchestrate
from brain.injection_guard import check_injection

from guardian.disk import get_disk_usage, format_size
from guardian.security import scan_system

from guardian.mode import set_mode, get_mode

from brain.memory import (
    add_permanent_memory,
    add_temporary_memory,
    get_all_memory,
    clear_temporary_memory
)

from guardian.system_control import (
    open_app,
    open_path,
    shutdown_system,
    restart_system,
    get_disk_status,
    clean_temp_files,
    scan_large_files,
    delete_path
)

from brain.dev_agent import read_file

import webbrowser


# =====================================================
# GLOBAL STATE
# =====================================================
pending_termination = None
pending_warning = None
pending_system_action = None
bypass_injection = False
last_response = ""


# =====================================================
# RESPONSE COMPRESSOR
# =====================================================
def compress_response(text):
    if not isinstance(text, str):
        return text

    if "\n" in text:
        return text.strip()

    if len(text) > 300:
        return text[:300] + "..."

    return text.strip()


# =====================================================
# MAIN ROUTER FUNCTION
# =====================================================
def route_command(user_input: str) -> str:
    global pending_termination
    global pending_warning
    global pending_system_action
    global bypass_injection
    global last_response

    lower = user_input.lower().strip()

    print(f"[Router] Input: {user_input}")

    # =====================================================
    # 🔥 MULTI COMMAND SUPPORT
    # =====================================================
    if " and " in lower:
        parts = user_input.split(" and ")
        responses = []

        for part in parts:
            responses.append(route_command(part.strip()))

        return "\n".join(responses)

    # =====================================================
    # CASUAL
    # =====================================================
    if lower in ["thank you", "thanks", "ok", "okay"]:
        return "You're welcome."

    # =====================================================
    # WARNING CONFIRMATION
    # =====================================================
    if pending_warning:
        if lower in ["yes", "y"]:
            cmd = pending_warning
            pending_warning = None
            bypass_injection = True
            return route_command(cmd)

        if lower in ["no", "n"]:
            pending_warning = None
            return "Command cancelled for safety."

    # =====================================================
    # SYSTEM CONFIRMATION
    # =====================================================
    if pending_system_action:
        if lower in ["yes", "y"]:
            action = pending_system_action
            pending_system_action = None

            if action == "shutdown":
                return shutdown_system()

            if action == "restart":
                return restart_system()

        if lower in ["no", "n"]:
            pending_system_action = None
            return "Cancelled."

    # =====================================================
    # INJECTION GUARD
    # =====================================================
    if bypass_injection:
        bypass_injection = False
        status, reason = "ALLOW", ""
    else:
        status, reason = check_injection(user_input)

    if status == "BLOCK":
        return f"⚠ BLOCKED: {reason}"

    if status == "WARN":
        pending_warning = user_input
        return f"⚠ WARNING: {reason}\nProceed? (yes/no)"

    # =====================================================
    # EXIT
    # =====================================================
    if lower == "exit":
        return "__EXIT__"

    # =====================================================
    # MODE
    # =====================================================
    if lower.startswith("mode "):
        mode = user_input.replace("mode ", "").strip()
        return set_mode(mode)

    if lower == "current mode":
        return f"Mode: {get_mode()}"

    # =====================================================
    # MEMORY
    # =====================================================
    if lower == "clear temporary memory":
        return clear_temporary_memory()

    if lower.startswith("remember this"):
        text = user_input.replace("remember this", "").strip()
        return add_permanent_memory(text)

    if lower.startswith("store temporary"):
        text = user_input.replace("store temporary", "").strip()
        return add_temporary_memory(text)

    if lower in ["what do you remember", "memory status"]:
        return get_all_memory()

    # =====================================================
    # SECURITY
    # =====================================================
    if lower.startswith("security scan"):
        result = scan_system()
        report = result["report"]
        suspect = result["suspect"]

        if suspect:
            pending_termination = suspect
            return compress_response(report) + \
                   f"\n\n⚠ Suspect: {suspect}\nTerminate? (yes/no)"

        return compress_response(report)

    # =====================================================
    # 🔥 DISK / STORAGE (PRIORITY)
    # =====================================================
    if "what takes my" in lower and "storage" in lower:
        return scan_large_files("C:\\")

    if any(x in lower for x in ["storage", "space", "disk usage"]):
        return get_disk_status()

    if any(x in lower for x in ["large file", "big files", "heavy files"]):
        return scan_large_files("C:\\")

    if any(x in lower for x in ["clean temp", "clear temp", "temporary files"]):
        return clean_temp_files()

    # =====================================================
    # DELETE (SAFE)
    # =====================================================
    if lower.startswith("delete "):
        path = user_input.replace("delete ", "").strip()
        return delete_path(path)

    # =====================================================
    # OPEN + SEARCH (COMBINED)
    # =====================================================
    if "open" in lower and "search" in lower:
        try:
            parts = lower.split("search")
            app_part = parts[0].replace("open", "").strip()
            query = parts[1].strip()

            open_app(app_part)
            webbrowser.open(f"https://www.google.com/search?q={query}")

            return f"Opening {app_part} and searching {query}"
        except:
            return "Couldn't process combined command."

    # =====================================================
    # OPEN (SMART)
    # =====================================================
    if lower.startswith("open "):
        target = user_input.replace("open ", "").strip().lower()

        # 🔥 CLEAN "drive" / "disk"
        target = target.replace("drive", "").replace("disk", "").strip()

        # 🔥 DRIVE (c, d, etc.)
        if len(target) == 1:
            return open_path(target)

        if target.endswith(":"):
            return open_path(target)

        # 🔥 PATH
        if "\\" in target or ":" in target:
            return open_path(target)

        return open_app(target)

    # =====================================================
    # SYSTEM CONTROL
    # =====================================================
    if "shutdown" in lower:
        pending_system_action = "shutdown"
        return "⚠ Shutdown system? (yes/no)"

    if "restart" in lower:
        pending_system_action = "restart"
        return "⚠ Restart system? (yes/no)"

    # =====================================================
    # ORCHESTRATOR
    # =====================================================
    result = orchestrate(user_input)

    if isinstance(result, dict):

        action = result.get("action")
        target = result.get("target")

        if action == "terminate":
            pending_termination = target
            return f"Terminate {target}? (yes/no)"

        if action == "dev_read":
            return read_file(target)

        if "message" in result:
            return compress_response(result["message"])

    # =====================================================
    # FALLBACK (LLM)
    # =====================================================
    response = ask_llm(user_input)

    if not response:
        return "I didn't catch that properly."

    if response == last_response:
        return "I already answered that."

    last_response = response

    print(f"[Router] Output: {response}")

    return response