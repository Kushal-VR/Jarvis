from brain.llm import ask_llm
from guardian.security import scan_system
import json
from guardian.security import WHITELIST_FILE, load_whitelist, save_whitelist
from guardian.mode import set_mode, get_mode

def route_command(user_input: str) -> str:
    lower = user_input.lower()
    # Mode commands
    if lower.startswith("mode "):
     mode = user_input.replace("mode ", "").strip()
     return set_mode(mode)

    if lower == "current mode":
      return f"Current defense mode: {get_mode()}"

    # Exit shortcut
    if lower in ["exit", "quit"]:
        return "__EXIT__"

    # Future: cybersecurity commands
    if lower.startswith("security status"):
        return "Cyber-Guardian running in Passive Mode."
    
    if lower.startswith("security scan"):
        return scan_system()
    
    if lower.startswith("approve "):
      path = user_input.replace("approve ", "").strip()
      
      whitelist = load_whitelist()
      whitelist["approved_paths"].append(path)
      save_whitelist(whitelist)

    return f"Approved and whitelisted: {path}"


    # Default → LLM
    return ask_llm(user_input)
