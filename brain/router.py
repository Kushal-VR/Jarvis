# =====================================================
# ROUTER - EXECUTION LAYER (CLEANED + FIXED)
# =====================================================

from brain.llm import ask_llm
from brain.orchestrator import orchestrate
from brain.injection_guard import check_injection

from guardian.disk import get_disk_usage, scan_large_files, format_size
from guardian.security import (
    scan_system,
    terminate_process_by_name,
)

from guardian.mode import set_mode, get_mode

from brain.memory import (
    add_permanent_memory,
    add_temporary_memory,
    get_all_memory,
    clear_temporary_memory
)

from guardian.system_control import (
    open_app,
    shutdown_system,
    restart_system,
    get_disk_status,
    clean_temp_files
)

from brain.dev_agent import read_file

import os


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
    """
    Smart compression without breaking structured output
    """

    if not isinstance(text, str):
        return text

    # 🔥 DO NOT break numbered lists or multi-line output
    if "\n" in text:
        return text.strip()

    # only shorten long plain sentences
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
    # SECURITY (DIRECT)
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
    # DISK
    # =====================================================
    if "disk usage" in lower:
        size = get_disk_usage("C:\\")
        return f"Disk usage: {format_size(size)}"

    if "large files" in lower:
        return scan_large_files("C:\\")

    if "disk status" in lower:
        return get_disk_status()

    if "clean temp" in lower:
        return clean_temp_files()

    # =====================================================
    # SYSTEM CONTROL
    # =====================================================
    if lower.startswith("open "):
        app = user_input.replace("open ", "").strip()
        return open_app(app)

    if "shutdown" in lower:
        pending_system_action = "shutdown"
        return "⚠ Shutdown system? (yes/no)"

    if "restart" in lower:
        pending_system_action = "restart"
        return "⚠ Restart system? (yes/no)"

    # =====================================================
    # 🧠 ORCHESTRATOR (FINAL AUTHORITY)
    # =====================================================
    result = orchestrate(user_input)

    if isinstance(result, dict):

        action = result.get("action")
        target = result.get("target")

        # 🔥 HANDLE ACTIONS
        if action == "terminate":
            pending_termination = target
            return f"Terminate {target}? (yes/no)"

        if action == "dev_read":
            return read_file(target)

        # 🔥 MOST IMPORTANT FIX → RETURN MESSAGE DIRECTLY
        if "message" in result:
            return compress_response(result["message"])

    # =====================================================
    # FALLBACK (LLM)
    # =====================================================
    response = ask_llm(user_input)

    if not response:
        return "I didn't catch that properly."

    # =====================================================
    # ANTI-REPEAT
    # =====================================================
    if response == last_response:
        return "I already answered that."

    last_response = response

    print(f"[Router] Output: {response}")

    return response