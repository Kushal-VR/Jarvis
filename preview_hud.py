import time
import threading
import sys
import os

# Ensure workspace packages can be imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from jarvis.ui import JarvisOverlay

def main():
    print("========================================")
    print("       Jarvis Arc Reactor HUD Preview   ")
    print("========================================")
    print("Initializing HUD Overlay...")
    
    # Enable UTF-8 console output just in case
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass

    overlay = JarvisOverlay()
    
    def command_handler(cmd):
        print(f"\n[HUD Entry] User sent command: '{cmd}'")
        overlay.reset_sleep_timer()
        
        # Determine some states or answers for fun
        cmd_lower = cmd.lower()
        if "sleep" in cmd_lower:
            overlay.set_state(overlay.STATE_SLEEPING)
            overlay.show_text("Going to sleep...")
        elif "listen" in cmd_lower:
            overlay.set_state(overlay.STATE_LISTENING)
            overlay.show_text("Listening for command...")
        elif "think" in cmd_lower:
            overlay.set_state(overlay.STATE_THINKING)
            overlay.show_text("Thinking of response...")
        elif "speak" in cmd_lower or "say" in cmd_lower:
            overlay.set_state(overlay.STATE_SPEAKING)
            overlay.show_text("I am Jarvis, your personal operating assistant. How can I help you today?")
        else:
            overlay.set_state(overlay.STATE_THINKING)
            # Simulate a quick thought process
            time.sleep(1.2)
            overlay.set_state(overlay.STATE_SPEAKING)
            overlay.show_text(f"Executed: {cmd}. Response generated successfully.")
            time.sleep(2.0)
            overlay.set_state(overlay.STATE_IDLE)

    overlay.set_command_callback(command_handler)
    
    print("\nHUD is active. You can:")
    print("1. Drag the HUD window around by clicking and holding anywhere.")
    print("2. Click '◈ JARVIS' title to minimize it to a bubble.")
    print("3. Type commands in the input box and click SEND or press Enter.")
    print("4. Try typing 'sleep', 'listen', 'think', or 'speak' to preview reactor animations.")
    print("\nPress Ctrl+C in this console or close the HUD to exit.")
    
    try:
        while overlay._running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nExiting HUD preview...")
    finally:
        overlay.destroy_safe()

if __name__ == "__main__":
    main()
