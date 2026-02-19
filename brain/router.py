# =====================================================
# ROUTER - COMMAND EXECUTION LAYER
# =====================================================

from brain.llm import ask_llm
from brain.orchestrator import orchestrate
from brain.injection_guard import check_injection

from guardian.security import (
    scan_system,
    terminate_process_by_name,
    load_whitelist,
    save_whitelist,
)

from guardian.mode import set_mode, get_mode

from brain.memory import (
    add_permanent_memory,
    add_temporary_memory,
    get_all_memory
)

# =====================================================
# GLOBAL STATE
# =====================================================
pending_termination = None
pending_warning = None
bypass_injection = False
last_response = ""

# =====================================================
# SIMILARITY CHECK
# =====================================================
def is_similar(a, b):
    """
    Simple similarity check (fast, offline)
    """
    if not a or not b:
        return False

    a_words = set(a.lower().split())
    b_words = set(b.lower().split())

    overlap = len(a_words & b_words)

    return overlap >= max(2, min(len(a_words), len(b_words)) // 2)


# =====================================================
# RESPONSE COMPRESSOR (VOICE OPTIMIZED)
# =====================================================
def compress_response(text):
    """
    Makes responses short for voice interaction
    """
    if not isinstance(text, str):
        return text

    # cut long responses
    if len(text) > 200:
        text = text.split(".")[0]

    return text.strip()


# =====================================================
# MAIN ROUTER FUNCTION
# =====================================================
def route_command(user_input: str) -> str:
    global pending_termination
    global pending_warning
    global bypass_injection
    global last_response

    lower = user_input.lower().strip()

    # =====================================================
    # STEP 1 — HANDLE WARNING CONFIRMATION
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
    # STEP 2 — INJECTION GUARD
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
        return f"⚠ WARNING: {reason}\nDo you want to proceed? (yes/no)"

    # =====================================================
    # STEP 3 — BASIC COMMANDS
    # =====================================================
    if lower in ["exit", "quit"]:
        return "__EXIT__"

    # =====================================================
    # MODE COMMANDS
    # =====================================================
    if lower.startswith("mode "):
        mode = user_input.replace("mode ", "").strip()
        return set_mode(mode)

    if lower == "current mode":
        return f"Current defense mode: {get_mode()}"

    # =====================================================
    # MEMORY SYSTEM
    # =====================================================
    if lower.startswith("remember this"):
        text = user_input.replace("remember this", "").strip()
        return add_permanent_memory(text)

    if lower.startswith("store temporary"):
        text = user_input.replace("store temporary", "").strip()
        return add_temporary_memory(text)

    if lower in ["what do you remember", "memory status"]:
        return get_all_memory()

    # =====================================================
    # SECURITY COMMANDS
    # =====================================================
    if lower.startswith("security status"):
        return f"Cyber-Guardian running in {get_mode()} mode."

    if lower.startswith("security scan"):

        result = scan_system()
        report = result["report"]
        suspect = result["suspect"]

        if suspect:
            pending_termination = suspect
            return compress_response(report) + \
                   f"\n\n⚠ Suspected process: {suspect}\nTerminate? (yes/no)"

        return compress_response(report)

    # =====================================================
    # WHITELIST
    # =====================================================
    if lower.startswith("approve "):
        path = user_input.replace("approve ", "").strip()

        whitelist = load_whitelist()

        if path not in whitelist["approved_paths"]:
            whitelist["approved_paths"].append(path)
            save_whitelist(whitelist)
            return f"Approved: {path}"
        else:
            return "Already approved."

    # =====================================================
    # TERMINATION FLOW
    # =====================================================
    if pending_termination:

        if lower in ["yes", "y"]:
            result = terminate_process_by_name(pending_termination)
            pending_termination = None
            return result

        if lower in ["no", "n"]:
            proc = pending_termination
            pending_termination = None
            return f"{proc} allowed."

    # =====================================================
    # MANUAL TERMINATE
    # =====================================================
    if lower.startswith("terminate "):
        process_name = user_input.replace("terminate ", "").strip()
        pending_termination = process_name
        return f"Terminate {process_name}? (yes/no)"

    # =====================================================
    # DEFAULT → ORCHESTRATOR
    # =====================================================
    result = orchestrate(user_input)

    if isinstance(result, dict):

        if result.get("action") == "terminate":
            pending_termination = result["target"]

            response = compress_response(result["message"]) + \
                       f"\n\nTerminate {result['target']}? (yes/no)"

        else:
            response = compress_response(result.get("message", ""))

    else:
        response = compress_response(result)

    # =====================================================
    # PREVENT REPEATED RESPONSES (SMART)
    # =====================================================
    if is_similar(response, last_response):
      return "Already answered."

    last_response = response
    return response

