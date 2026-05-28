import os
import subprocess
import time
import logging
import pyautogui

class OSController:
    def __init__(self):
        self.logger = logging.getLogger("Jarvis.OSControl")

    def open_application(self, app_name: str):
        """
        Attempts to launch an application.
        If direct launch fails, falls back to Windows Search.
        """
        self.logger.info(f"Attempting to launch application: '{app_name}'")
        
        # Heuristics for common app names to executable path mapping
        common_apps = {
            "chrome": ["chrome.exe", "google-chrome"],
            "edge": ["msedge.exe"],
            "notepad": ["notepad.exe"],
            "calculator": ["calc.exe"],
            "paint": ["mspaint.exe"],
            "explorer": ["explorer.exe"]
        }

        app_clean = app_name.strip().lower()
        commands_to_try = common_apps.get(app_clean, [f"{app_name}.exe", app_name])

        launched = False
        for cmd in commands_to_try:
            try:
                # Use Windows shell start command which handles system PATH associations
                subprocess.Popen(f"start {cmd}", shell=True)
                self.logger.info(f"Successfully launched app using command: {cmd}")
                launched = True
                break
            except Exception as e:
                self.logger.debug(f"Direct start command failed for {cmd}: {e}")

        if not launched:
            self.logger.warning(f"Could not launch '{app_name}' directly. Attempting Windows Search fallback...")
            try:
                self._windows_search_launch(app_name)
            except Exception as e:
                self.logger.error(f"Windows Search fallback failed: {e}")
                raise RuntimeError(f"Could not open application '{app_name}' through command line or search.")

    def _windows_search_launch(self, app_name: str):
        """
        Falls back to Windows GUI search sequence:
        1. Press Win key to open Start Menu.
        2. Wait for Start Menu to render.
        3. Type application name.
        4. Wait for match.
        5. Press Enter.
        """
        self.logger.info(f"Executing Windows Search sequence for: {app_name}")
        pyautogui.press('win')
        time.sleep(1.0) # Wait for start menu
        pyautogui.write(app_name, interval=0.05)
        time.sleep(1.0) # Wait for search matches
        pyautogui.press('enter')
        self.logger.info("Windows Search launch sequence executed.")

    def close_application(self, app_name: str):
        """
        Force closes a process using taskkill.
        """
        self.logger.info(f"Attempting to close application: '{app_name}'")
        exe_name = app_name if app_name.lower().endswith(".exe") else f"{app_name}.exe"
        try:
            cmd = f"taskkill /f /im {exe_name}"
            result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode == 0:
                self.logger.info(f"Successfully terminated application '{exe_name}'")
            else:
                self.logger.warning(f"Process kill command returned non-zero. App may not have been running. output: {result.stderr}")
        except Exception as e:
            self.logger.error(f"Failed to kill application '{exe_name}': {e}")
            raise
