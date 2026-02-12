import psutil
from collections import defaultdict
import os
import json
from guardian.mode import get_mode
import winreg


SYSTEM_PROCESS_ALLOWLIST = [
    "svchost.exe",
    "WUDFHost.exe",
    "SystemSettings.exe",
    "NVDisplay.Container.exe",
    "ipfsvc.exe"
]


def scan_startup_registry():
    report = []
    run_keys = [
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        r"Software\Microsoft\Windows\CurrentVersion\RunOnce"
    ]

    for key_path in run_keys:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        report.append(f"{name} → {value}")
                        i += 1
                    except OSError:
                        break
        except FileNotFoundError:
            continue

    return report



def calculate_risk(name, exe_path, connection_count, whitelisted):
    score = 0
    reasons = []

    # Ignore core Windows processes
    if name in SYSTEM_PROCESS_ALLOWLIST:
        return 0, []

    unusual_path = exe_path and is_suspicious_path(exe_path)

    if unusual_path:
        score += 30
        reasons.append("Unusual executable location")

    if not whitelisted and unusual_path:
        score += 20
        reasons.append("Not in whitelist")

    if connection_count > 5:
        score += 15
        reasons.append("High outbound activity")

    if exe_path and any(x in exe_path.lower() for x in ["temp", "downloads"]):
        score += 25
        reasons.append("Running from temp/downloads")

    return score, reasons


WHITELIST_FILE = "guardian/whitelist.json"


def load_whitelist():
    try:
        with open(WHITELIST_FILE, "r") as f:
            return json.load(f)
    except:
        return {"approved_paths": []}


def save_whitelist(data):
    with open(WHITELIST_FILE, "w") as f:
        json.dump(data, f, indent=4)


SAFE_PATHS = [
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "C:\\Users",
    "C:\\ProgramData"
]



def is_suspicious_path(path):
    if not path:
        return True

    for safe in SAFE_PATHS:
        if path.startswith(safe):
            return False

    return True


def scan_system():
    report = []

    processes = list(psutil.process_iter(['pid', 'name', 'exe']))
    report.append(f"Running processes: {len(processes)}")

    suspicious = []

    for proc in processes:
        try:
            exe_path = proc.info['exe']
            name = proc.info['name']
            
            whitelist = load_whitelist()
           
            if exe_path and is_suspicious_path(exe_path):
              if name not in ["Registry", "MemCompression"]:
                if exe_path not in whitelist["approved_paths"]:
                  suspicious.append((name, exe_path))


        except Exception:
            pass

    connections = psutil.net_connections(kind='inet')
    process_connections = defaultdict(int)

    for conn in connections:
        if conn.raddr and conn.pid:
            try:
                process = psutil.Process(conn.pid)
                name = process.name()
                process_connections[name] += 1
            except Exception:
                pass

    total_outbound = sum(process_connections.values())
    report.append(f"Active outbound connections: {total_outbound}")

    if process_connections:
        sorted_procs = sorted(
            process_connections.items(),
            key=lambda x: x[1],
            reverse=True
        )

        report.append("Top network-active processes:")
        for name, count in sorted_procs[:5]:
            report.append(f" - {name}: {count} connections")

    if suspicious:
        report.append("\n⚠ Suspicious process locations detected:")
        for name, path in suspicious[:5]:
            report.append(f" - {name} running from {path}")

    else:
        report.append("\nNo suspicious process locations detected.")

        report.append("\nRisk Analysis:")

        whitelist = load_whitelist()

    for name, count in process_connections.items():
        try:
            proc = next(p for p in processes if p.info['name'] == name)
            exe_path = proc.info['exe']
        except:
            exe_path = None

        whitelisted = exe_path in whitelist["approved_paths"] if exe_path else False

        score, reasons = calculate_risk(name, exe_path, count, whitelisted)

        if score > 0:
            if score <= 20:
                level = "LOW"
            elif score <= 50:
                level = "MEDIUM"
            elif score <= 80:
                level = "HIGH"
            else:
                level = "CRITICAL"

            report.append(f"\n{name} → Risk Score: {score} ({level})")
            for r in reasons:
                report.append(f"   - {r}")
       
        # Escalation logic
    mode = get_mode()

    highest_score = 0
    for name, count in process_connections.items():
        try:
            proc = next(p for p in processes if p.info['name'] == name)
            exe_path = proc.info['exe']
        except:
            exe_path = None

        whitelisted = exe_path in whitelist["approved_paths"] if exe_path else False
        score, _ = calculate_risk(name, exe_path, count, whitelisted)

        if score > highest_score:
            highest_score = score

    if mode == "GUARD" and highest_score >= 50:
        report.append("\n⚠ GUARD MODE ALERT: High risk detected. Review recommended.")

    if mode == "LOCKDOWN" and highest_score >= 80:
        report.append("\n☠ LOCKDOWN MODE ALERT: Critical risk detected. Immediate approval required.")
   
        report.append("\nStartup Registry Entries:")

    startup_entries = scan_startup_registry()

    if startup_entries:
        for entry in startup_entries:
            report.append(f" - {entry}")
    else:
        report.append(" No startup registry entries found.")



    return "\n".join(report)
