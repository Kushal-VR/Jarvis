from brain.llm import ask_llm
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


# =====================================================
# MAIN ROUTER
# =====================================================
def route_command(user_input: str) -> str:
    global pending_termination
    global pending_warning
    global bypass_injection

    lower = user_input.lower().strip()

    # =====================================================
    # STEP 1 — HANDLE WARNING CONFIRMATION FIRST
    # =====================================================
    if pending_warning:

        if lower in ["yes", "y"]:
            cmd = pending_warning
            pending_warning = None
            bypass_injection = True  # allow next execution
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

    # -------------------------------------------------
    # MODE COMMANDS
    # -------------------------------------------------
    if lower.startswith("mode "):
        mode = user_input.replace("mode ", "").strip()
        return set_mode(mode)

    if lower == "current mode":
        return f"Current defense mode: {get_mode()}"

    # =====================================================
    # STEP 4 — MEMORY SYSTEM
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
    # STEP 5 — SECURITY SYSTEM
    # =====================================================
    if lower.startswith("security status"):
        return f"Cyber-Guardian running in {get_mode()} mode."

    if lower.startswith("security scan"):

        result = scan_system()
        report = result["report"]
        suspect = result["suspect"]

        if suspect:
            pending_termination = suspect
            return (
                report +
                f"\n\n⚠ High file activity detected.\n"
                f"Suspected process: {suspect}\n"
                f"Do you want to terminate it? (yes/no)"
            )

        return report

    # =====================================================
    # STEP 6 — WHITELIST
    # =====================================================
    if lower.startswith("approve "):
        path = user_input.replace("approve ", "").strip()

        whitelist = load_whitelist()

        if path not in whitelist["approved_paths"]:
            whitelist["approved_paths"].append(path)
            save_whitelist(whitelist)
            return f"Approved and whitelisted: {path}"
        else:
            return "Path already whitelisted."

    # =====================================================
    # STEP 7 — TERMINATION FLOW
    # =====================================================
    if pending_termination:

        if lower in ["yes", "y"]:
            result = terminate_process_by_name(pending_termination)
            pending_termination = None
            return result

        if lower in ["no", "n"]:
            proc = pending_termination
            pending_termination = None
            return f"Process {proc} will be allowed to continue."

    # -------------------------------------------------
    # MANUAL TERMINATE (after injection approval)
    # -------------------------------------------------
    if lower.startswith("terminate "):
        process_name = user_input.replace("terminate ", "").strip()
        pending_termination = process_name
        return f"Do you want to terminate {process_name}? (yes/no)"

    # =====================================================
    # STEP 8 — DEFAULT (LLM)
    # =====================================================
    return ask_llm(user_input)
