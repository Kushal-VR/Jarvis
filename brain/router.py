from brain.llm import ask_llm
from guardian.security import (
    scan_system,
    terminate_process_by_name,
    load_whitelist,
    save_whitelist,
)
from guardian.mode import set_mode, get_mode

pending_termination = None


def route_command(user_input: str) -> str:
    global pending_termination

    lower = user_input.lower().strip()

    # Exit
    if lower in ["exit", "quit"]:
        return "__EXIT__"

    # Mode commands
    if lower.startswith("mode "):
        mode = user_input.replace("mode ", "").strip()
        return set_mode(mode)

    if lower == "current mode":
        return f"Current defense mode: {get_mode()}"

    # Security status
    if lower.startswith("security status"):
        return f"Cyber-Guardian running in {get_mode()} mode."

    # SECURITY SCAN (AUTO TERMINATION FLOW)
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

    # Whitelist
    if lower.startswith("approve "):
        path = user_input.replace("approve ", "").strip()
        whitelist = load_whitelist()

        if path not in whitelist["approved_paths"]:
            whitelist["approved_paths"].append(path)
            save_whitelist(whitelist)
            return f"Approved and whitelisted: {path}"
        else:
            return "Path already whitelisted."

    # Termination confirmation
    if pending_termination:
        if lower in ["yes", "y"]:
            result = terminate_process_by_name(pending_termination)
            pending_termination = None
            return result

        if lower in ["no", "n"]:
            proc = pending_termination
            pending_termination = None
            return f"Process {proc} will be allowed to continue."

    # Manual terminate
    if lower.startswith("terminate "):
        process_name = user_input.replace("terminate ", "").strip()
        pending_termination = process_name
        return f"Do you want to terminate {process_name}? (yes/no)"

    # Default → LLM
    return ask_llm(user_input)
