# =====================================================
# ORCHESTRATOR - CENTRAL DECISION ENGINE
# This is the "brain above router"
# It decides WHAT action to take (not just route commands)
# =====================================================

from pydoc import text

from guardian.security import scan_system, terminate_process_by_name
from brain.memory import get_all_memory
from brain.llm import ask_llm
from brain.dev_agent import read_file





# =====================================================
# HELPER: EXTRACT HIGH-RISK PROCESS FROM REPORT
# This reads scan output and finds risky processes
# =====================================================
def detect_risky_process(report_text):
    """
    Parses scan report and finds highest-risk process.

    Returns:
        process_name (str) OR None
    """

    lines = report_text.split("\n")
    risky = []

    for line in lines:
        # Look for lines like:
        # chrome.exe → Risk Score: 35 (MEDIUM)
        if "→ Risk Score:" in line:
            try:
                name = line.split("→")[0].strip()
                score = int(line.split("Risk Score:")[1].split()[0])

                # Only consider meaningful risk
                if score >= 20:
                    risky.append((name, score))

            except:
                continue

    if not risky:
        return None

    # Sort by highest risk
    risky.sort(key=lambda x: x[1], reverse=True)

    return risky[0][0]  # return process name


# =====================================================
# MAIN ORCHESTRATOR FUNCTION
# =====================================================
def orchestrate(user_input: str):
    """
    Central brain:
    Decides WHAT to do before router executes it.

    Returns structured response:
    {
        "action": optional (e.g., terminate),
        "target": optional (process name),
        "message": string output
    }
    """

    text = user_input.lower()
    
    # -------------------------------
    # DEV AGENT INTENT (SMART PARSING)
    # -------------------------------
    words = text.split()
    if "create file" in text:
      # try to get filename
      if len(words) >= 3:
        filename = words[-1]
        return {
            "action": "dev_create",
            "target": filename
        }
      else:
        return {"message": "Please specify file name clearly."}


    if "read file" in text:

       if len(words) >= 3:
        filename = words[-1]
        return {
            "action": "dev_read",
            "target": filename
        }
       else:
        return {"message": "Please specify file name clearly."}
   
    # =====================================================
    # SECURITY: FULL SYSTEM SCAN
    # =====================================================
    if "check system" in text or "scan system" in text:
        result = scan_system()

        return {
            "message": result["report"]
        }

    # =====================================================
    # SECURITY: CLOSE RISKY APPS (SMART DECISION)
    # =====================================================
    if "close risky" in text or "stop threat" in text:
        result = scan_system()

        report = result["report"]

        # First priority → disk spike suspect
        suspect = result.get("suspect")

        if suspect:
            return {
                "action": "terminate",
                "target": suspect,
                "message": (
                    report +
                    f"\n\n⚠ High-risk activity detected.\n"
                    f"Suspected process: {suspect}"
                )
            }

        # Second → parse report for risky processes
        risky_process = detect_risky_process(report)

        if risky_process:
            return {
                "action": "terminate",
                "target": risky_process,
                "message": (
                    report +
                    f"\n\n⚠ Suggested action:\n"
                    f"Terminate {risky_process}?"
                )
            }

        # If nothing risky
        return {
            "message": report + "\n\nNo high-risk processes found."
        }

    # =====================================================
    # MEMORY: RECALL
    # =====================================================
    if "what do you remember" in text:
        return {
            "message": get_all_memory()
        }

    # =====================================================
    # DEFAULT: LLM THINKING
    # =====================================================
    response = ask_llm(user_input)

    return {
        "message": response
    }
