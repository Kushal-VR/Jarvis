"""
register_startup.py
===================
One-time script to register (or unregister) Jarvis as a Windows auto-startup
application via the HKCU Registry Run key.

Usage:
    python register_startup.py              # Register auto-startup
    python register_startup.py --unregister # Remove auto-startup
"""

import os
import sys
import winreg
import argparse

APP_NAME    = "JarvisAI"
REG_PATH    = r"Software\Microsoft\Windows\CurrentVersion\Run"
VBS_SCRIPT  = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "jarvis_launcher.vbs")


def register():
    """Write the startup registry entry."""
    if not os.path.exists(VBS_SCRIPT):
        print(f"[ERROR] Launcher script not found: {VBS_SCRIPT}")
        sys.exit(1)

    launch_cmd = f'wscript.exe "{VBS_SCRIPT}"'

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            REG_PATH, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, launch_cmd)

        print("=" * 56)
        print("  [OK]  Jarvis Auto-Startup REGISTERED successfully!")
        print(f"     Registry key : HKCU\\{REG_PATH}")
        print(f"     Entry name   : {APP_NAME}")
        print(f"     Command      : {launch_cmd}")
        print("=" * 56)
        print("  Jarvis will now start automatically every time you")
        print("  log in to Windows.")
        print("  To remove: python register_startup.py --unregister")
        print("=" * 56)

    except PermissionError:
        print("[ERROR] Permission denied writing to registry.")
        print("  Try running this script as Administrator.")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Failed to register startup: {e}")
        sys.exit(1)


def unregister():
    """Remove the startup registry entry."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            REG_PATH, 0,
                            winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, APP_NAME)
                print("=" * 56)
                print("  [OK]  Jarvis Auto-Startup UNREGISTERED successfully.")
                print("     Jarvis will no longer start automatically.")
                print("=" * 56)
            except FileNotFoundError:
                print("  [INFO] No startup entry found — nothing to remove.")

    except Exception as e:
        print(f"[ERROR] Failed to unregister startup: {e}")
        sys.exit(1)


def check_status():
    """Check if the startup entry exists."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            REG_PATH, 0,
                            winreg.KEY_READ) as key:
            try:
                val, _ = winreg.QueryValueEx(key, APP_NAME)
                print(f"  [OK] Startup REGISTERED -> {val}")
                return True
            except FileNotFoundError:
                print("  [X]  Startup NOT registered.")
                return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Jarvis Startup Registration Tool")
    parser.add_argument(
        "--unregister", action="store_true",
        help="Remove Jarvis from Windows startup")
    parser.add_argument(
        "--status", action="store_true",
        help="Check if startup is registered")
    args = parser.parse_args()

    if args.status:
        check_status()
    elif args.unregister:
        unregister()
    else:
        register()
