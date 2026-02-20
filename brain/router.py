# =====================================================
# ROUTER - COMMAND EXECUTION LAYER
# Handles:
# - Security (Injection Guard)
# - Memory
# - System Commands
# - Orchestrator fallback
# =====================================================

from brain.llm import ask_llm
from brain.orchestrator import orchestrate
from brain.injection_guard import check_injection

from guardian.disk import get_disk_usage, scan_large_files, format_size

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
# NORMALIZE VOICE COMMANDS
# Fixes messy voice inputs
# =====================================================
def normalize_command(text: str) -> str:
    text = text.lower()

    # =========================================
    # 🔥 MEMORY NORMALIZATION
    # =========================================
    if any(x in text for x in ["clear", "delete", "remove"]) and \
       any(x in text for x in ["temporary", "temp"]):
        return "clear temporary memory"

    if "memory" in text and ("what" in text or "show" in text):
        return "memory status"

    # =========================================
    # 🔥 SECURITY NORMALIZATION
    # =========================================
    if "security" in text and "scan" in text:
        return "security scan"

    if "scan system" in text:
        return "security scan"

    # =========================================
    # 🔥 EXIT NORMALIZATION
    # =========================================
    if "exit" in text or "stop" in text or "quit" in text:
        return "exit"

    # =========================================
    # 🔥 APP CONTROL (future ready)
    # =========================================
    if "open chrome" in text:
        return "open chrome"

    # =========================================
    # DEFAULT
    # =========================================
    return text


# =====================================================
# SIMILARITY CHECK (ANTI-SPAM)
# =====================================================
def is_similar(a, b):
    if not a or not b:
        return False

    a_words = set(a.lower().split())
    b_words = set(b.lower().split())

    overlap = len(a_words & b_words)
    return overlap >= max(2, min(len(a_words), len(b_words)) // 2)


# =====================================================
# RESPONSE COMPRESSOR (VOICE FRIENDLY)
# =====================================================
def compress_response(text):
    if not isinstance(text, str):
        return text

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

    # 🔥 Normalize voice input
    user_input = normalize_command(user_input)
    lower = user_input.lower().strip()
    
    # CASUAL RESPONSES
    if lower in ["thank you", "thanks", "ok", "okay"]:
      return "You're welcome."
    
    # =====================================================
    # STEP 1 — WARNING CONFIRMATION
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
        return f"⚠ WARNING: {reason}\nProceed? (yes/no)"

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
        return f"Mode: {get_mode()}"

    # =====================================================
    # MEMORY SYSTEM
    # =====================================================
    # CLEAR TEMP MEMORY
    if lower == "clear temporary memory":
     from brain.memory import clear_temporary_memory
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
    # SECURITY SYSTEM
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
                   f"\n\n⚠ Suspect: {suspect}\nTerminate? (yes/no)"

        return compress_response(report)
    # =========================================
    # FILE COMMANDS
    # =========================================
    if "read" in lower and ".py" in lower:

       import os

       # extract filename
       words = lower.split()
       filename = None

       for w in words:
           if ".py" in w:
              filename = w
              break
 
       if not filename:
          return "Please specify file name clearly."

        # try to find file in project
       base_path = os.getcwd()

       for root, dirs, files in os.walk(base_path):
           if filename in files:
               file_path = os.path.join(root, filename)

               try:
                    with open(file_path, "r", encoding="utf-8") as f:
                     content = f.read()

                    return f"Reading {filename}:\n" + content[:1000]

               except Exception as e:
                  return f"Error reading file: {e}"

       return f"{filename} not found."
    
    # =====================================================
    # DISK SYSTEM (NEW 🔥)
    # =====================================================
    if "disk usage" in lower:
        size = get_disk_usage("C:\\")
        return f"Disk usage: {format_size(size)}"

    if "large files" in lower:
        return scan_large_files("C:\\")

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
    # DEFAULT → ORCHESTRATOR + LLM FALLBACK
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
    # 🔥 FINAL FALLBACK (FIXED)
    # =====================================================
    if not response or response.strip() == "":
     response = ask_llm(user_input)

    # 🔥 STILL EMPTY → SAFE RESPONSE
    if not response or response.strip() == "":
      return "I didn't catch that properly."

    return response