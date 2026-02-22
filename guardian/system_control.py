# =====================================================
# SYSTEM CONTROL MODULE (FINAL STABLE VERSION)
# =====================================================

import os
import subprocess
import shutil
import psutil


# =====================================================
# OPEN APPLICATIONS (SMART)
# =====================================================
def open_app(app_name: str):
    app_name = app_name.lower().strip()

    try:
        app_map = {
            "chrome": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "edge": "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "cmd": "cmd.exe",
            "explorer": "explorer.exe",
            "vscode": "code",
            "vs code": "code",
            "microsoft store": "start ms-windows-store:",  # 🔥 FIXED
        }

        if app_name in app_map:
            subprocess.Popen(app_map[app_name], shell=True)
            return f"Opening {app_name}"

        if "microsoft store" in app_name:
         subprocess.Popen("start ms-windows-store:", shell=True)
         return "Opening Microsoft Store"

        # fallback (windows search)
        subprocess.Popen(f'start "" "{app_name}"', shell=True)
        return f"Trying to open {app_name}"
        

    except Exception as e:
        return f"Failed to open {app_name}: {str(e)}"


# =====================================================
# OPEN PATH / DRIVE / FOLDER
# =====================================================
def open_path(path: str):
    try:
        path = path.strip()

        # 🔥 HANDLE DRIVE INPUTS
        if len(path) == 1:  # "c"
            path = path.upper() + ":\\"  

        elif len(path) == 2 and path[1] == ":":  # "c:"
            path = path.upper() + "\\"

        if os.path.exists(path):
            os.startfile(path)
            return f"Opening {path}"

        return f"Path not found: {path}"

    except Exception as e:
        return f"Error opening path: {str(e)}"


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
# DISK STATUS
# =====================================================
def get_disk_status():
    try:
        usage = psutil.disk_usage('C:\\')

        total = round(usage.total / (1024**3), 2)
        used = round(usage.used / (1024**3), 2)
        free = round(usage.free / (1024**3), 2)

        return f"Disk: {used} GB used / {total} GB total | Free: {free} GB"

    except Exception as e:
        return f"Disk check failed: {e}"


# =====================================================
# FIND LARGE FILES (OPTIMIZED ⚡)
# =====================================================
def scan_large_files(path="C:\\", limit_mb=100):
    large_files = []

    try:
        for root, dirs, files in os.walk(path):

            # 🔥 SKIP HEAVY SYSTEM FOLDERS (IMPORTANT)
            if any(x in root.lower() for x in ["windows", "program files", "appdata"]):
                continue

            for file in files:
                try:
                    file_path = os.path.join(root, file)
                    size = os.path.getsize(file_path) / (1024 * 1024)

                    if size > limit_mb:
                        large_files.append((file_path, round(size, 2)))

                except:
                    continue

        if not large_files:
            return "No large files found."

        large_files.sort(key=lambda x: x[1], reverse=True)

        result = "🔥 Large files:\n\n"
        for i, (file_path, size) in enumerate(large_files[:10], 1):
            result += f"{i}. {file_path} ({size} MB)\n"

        return result.strip()

    except Exception as e:
        return f"Scan failed: {e}"


# =====================================================
# DELETE FILE / FOLDER (SAFE ⚠️)
# =====================================================
def delete_path(path: str):
    try:
        path = path.strip()

        if not os.path.exists(path):
            return "Path not found."

        # 🔥 PROTECT SYSTEM PATHS
        protected = ["C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)"]

        for p in protected:
            if path.lower().startswith(p.lower()):
                return "❌ Protected system path. Cannot delete."

        if os.path.isfile(path):
            os.remove(path)
            return f"Deleted file: {path}"

        if os.path.isdir(path):
            shutil.rmtree(path)
            return f"Deleted folder: {path}"

        return "Unknown path type."

    except Exception as e:
        return f"Delete failed: {e}"


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
# RUN SHELL COMMAND (LIMITED)
# =====================================================
def run_command(cmd: str):
    try:
        result = subprocess.check_output(cmd, shell=True, text=True)
        return result[:500]
    except Exception as e:
        return f"Command failed: {e}"