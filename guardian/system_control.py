# =====================================================
# SYSTEM CONTROL MODULE (SAFE OS ACTIONS)
# =====================================================

import os
import subprocess
import shutil
import psutil


# =====================================================
# OPEN APPLICATIONS
# =====================================================
def open_app(app_name: str):
    app = app_name.lower()

    try:
        if "chrome" in app:
            subprocess.Popen("start chrome", shell=True)
            return "Opening Chrome."

        if "edge" in app:
            subprocess.Popen("start msedge", shell=True)
            return "Opening Edge."

        if "vscode" in app or "code" in app:
            subprocess.Popen("code", shell=True)
            return "Opening VS Code."

        if "notepad" in app:
            subprocess.Popen("notepad", shell=True)
            return "Opening Notepad."

        return "Application not recognized."

    except Exception as e:
        return f"Failed to open app: {e}"


# =====================================================
# SYSTEM POWER CONTROL
# =====================================================
def shutdown_system():
    os.system("shutdown /s /t 5")
    return "System shutting down in 5 seconds."


def restart_system():
    os.system("shutdown /r /t 5")
    return "System restarting in 5 seconds."


# =====================================================
# DISK USAGE
# =====================================================
def get_disk_status():
    usage = psutil.disk_usage('/')

    total = round(usage.total / (1024**3), 2)
    used = round(usage.used / (1024**3), 2)
    free = round(usage.free / (1024**3), 2)

    return f"Disk usage: {used} GB used, {free} GB free out of {total} GB."


# =====================================================
# CLEAN TEMP FILES
# =====================================================
def clean_temp_files():
    temp_path = os.getenv('TEMP')
    deleted = 0

    try:
        for file in os.listdir(temp_path):
            file_path = os.path.join(temp_path, file)

            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    deleted += 1
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                    deleted += 1
            except:
                continue

        return f"Cleaned {deleted} temporary files."

    except Exception as e:
        return f"Failed to clean temp files: {e}"


# =====================================================
# RUN SHELL COMMAND (SAFE)
# =====================================================
def run_command(cmd: str):
    try:
        result = subprocess.check_output(cmd, shell=True, text=True)
        return result[:500]  # limit output
    except Exception as e:
        return f"Command failed: {e}"