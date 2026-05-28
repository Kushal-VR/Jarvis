import tkinter as tk
from tkinter import messagebox
import sys
import logging
import threading
import time
import json

class PermissionManager:
    def __init__(self, permission_config: dict):
        self.config = permission_config
        self.logger = logging.getLogger("Jarvis.Security")
        self.voice_in = None
        self.voice_out = None

    def set_voice_systems(self, voice_in, voice_out):
        """Wire the voice input/output pipelines to enable voice-based confirmations."""
        self.voice_in = voice_in
        self.voice_out = voice_out

    def _show_gui_dialog(self, title: str, message: str) -> bool:
        """
        Displays a standard Tkinter dialog box on Windows for user consent.
        """
        try:
            root = tk.Tk()
            root.withdraw() # Hide primary window
            root.attributes("-topmost", True) # Force focus
            result = messagebox.askyesno(title, message)
            root.destroy()
            return result
        except Exception as e:
            self.logger.warning(f"Could not open GUI popup dialogue: {e}. Falling back to CLI console.")
            return self._show_cli_dialog(message)

    def _show_cli_dialog(self, message: str) -> bool:
        """
        Fallback console dialog.
        """
        print(f"\n[SECURITY CONFIRMATION REQUIRED]\n{message}")
        try:
            response = input("Proceed? (yes/no): ").strip().lower()
            return response in ["yes", "y"]
        except Exception:
            return False

    def request_approval(self, action_name: str, description: str, level: str) -> bool:
        """
        Verifies if an action is allowed based on the security level configuration.
        Supports both GUI buttons and spoken voice approval.
        """
        level = level.upper()
        if level == "LOW":
            self.logger.info(f"Automatically approved LOW-level action: {action_name}")
            return True
            
        title = f"Jarvis Permission Request - {level} RISK"
        message = f"Jarvis is requesting permission to perform the following action:\n\n" \
                  f"Action: {action_name}\n" \
                  f"Description: {description}"
                  
        if level == "HIGH":
            message = "⚠️ WARNING: HIGH RISK OPERATION DETECTED ⚠️\n\n" + message
            
        self.logger.warning(f"Requesting user approval for {level}-level action: {action_name}")
        
        # Speak request in parallel if voice systems are available
        if self.voice_out:
            self.voice_out.speak(f"Permission required for {action_name}. Say yes to approve or no to deny.", block=False)
            
        approved = self._show_dual_approval_dialog(title, message)
        
        if approved:
            self.logger.info(f"User APPROVED {level}-level action: {action_name}")
        else:
            self.logger.warning(f"User DENIED {level}-level action: {action_name}")
            
        return approved

    def _show_dual_approval_dialog(self, title: str, message: str) -> bool:
        """
        Shows a themed dark-blue dialog window that listens for both button clicks and spoken voice approval.
        """
        result = None
        voice_thread = None
        stop_listening_event = threading.Event()

        def on_yes():
            nonlocal result
            result = True
            stop_listening_event.set()
            try:
                root.destroy()
            except Exception:
                pass

        def on_no():
            nonlocal result
            result = False
            stop_listening_event.set()
            try:
                root.destroy()
            except Exception:
                pass

        try:
            root = tk.Tk()
            root.title(title)
            root.geometry("420x220")
            root.attributes("-topmost", True)
            root.configure(bg="#060a14")
            root.resizable(False, False)

            # Center window
            sw = root.winfo_screenwidth()
            sh = root.winfo_screenheight()
            x = (sw - 420) // 2
            y = (sh - 220) // 2
            root.geometry(f"420x220+{x}+{y}")

            lbl_msg = tk.Label(root, text=message, font=("Segoe UI", 10), fg="#c8e8ff", bg="#060a14", wraplength=380, justify="center")
            lbl_msg.pack(pady=(20, 10))

            status_text = "🎙️ Listening for voice approval ('yes' / 'no')..." if self.voice_in else "Please select an option below."
            lbl_status = tk.Label(root, text=status_text, font=("Segoe UI", 9, "italic"), fg="#00d4ff", bg="#060a14")
            lbl_status.pack(pady=5)

            btn_frame = tk.Frame(root, bg="#060a14")
            btn_frame.pack(pady=15)

            btn_yes = tk.Button(btn_frame, text="Yes (Approve)", width=16, command=on_yes, bg="#1c3a5e", fg="#c8e8ff", relief="flat", font=("Segoe UI", 9, "bold"))
            btn_yes.pack(side="left", padx=10)

            btn_no = tk.Button(btn_frame, text="No (Deny)", width=16, command=on_no, bg="#0f1a2e", fg="#c8e8ff", relief="flat", font=("Segoe UI", 9, "bold"))
            btn_no.pack(side="right", padx=10)

            root.bind("<Return>", lambda e: on_yes())
            root.bind("<Escape>", lambda e: on_no())

            # Start background voice listener thread
            if self.voice_in:
                def listen_voice():
                    start_time = time.time()
                    # Listen for up to 10 seconds or until user interacts
                    while not stop_listening_event.is_set() and time.time() - start_time < 10:
                        # Capture user speech
                        transcription = self.voice_in.record_and_transcribe(duration=3, bypass_delay=True)
                        t_lower = transcription.lower().strip("?.!, ")
                        if not t_lower:
                            continue
                        
                        self.logger.info(f"Voice approval listener heard: '{t_lower}'")
                        if any(w in t_lower for w in ["yes", "approve", "allow", "okay", "ok", "do it"]):
                            root.after(0, on_yes)
                            break
                        elif any(w in t_lower for w in ["no", "deny", "cancel", "stop", "don't"]):
                            root.after(0, on_no)
                            break

                voice_thread = threading.Thread(target=listen_voice, daemon=True, name="PermissionVoiceListener")
                voice_thread.start()

            root.mainloop()
        except Exception as e:
            self.logger.warning(f"Failed to display dual dialog: {e}. Falling back to CLI console.")
            result = self._show_cli_dialog(message)

        stop_listening_event.set()
        return result if result is not None else False
