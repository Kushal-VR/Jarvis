import psutil
from collections import defaultdict
import json
import winreg
import subprocess
from guardian.mode import get_mode
from guardian.folder_monitor import get_folder_risk


# =====================================================
# SYSTEM ALLOWLIST
# Trusted Windows processes ignored in scoring
# =====================================================
SYSTEM_PROCESS_ALLOWLIST = [
    "svchost.exe",
    "WUDFHost.exe",
    "SystemSettings.exe",
    "NVDisplay.Container.exe",
    "ipfsvc.exe"
    "Code.exe",
    "python.exe",

]


# =====================================================
# SAFE EXECUTION PATHS
# Anything outside these may be suspicious
# =====================================================
SAFE_PATHS = [
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "C:\\Users",
    "C:\\ProgramData"
]


# =====================================================
# WHITELIST STORAGE
# =====================================================
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


# =====================================================
# SAFE PROCESS TERMINATION
# =====================================================
def terminate_process_by_name(name):
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] == name:
                proc.terminate()
                return f"Process {name} terminated successfully."
        except:
            continue
    return f"Process {name} not found."


# =====================================================
# PATH CHECK
# =====================================================
def is_suspicious_path(path):
    if not path:
        return True
    for safe in SAFE_PATHS:
        if path.startswith(safe):
            return False
    return True


# =====================================================
# PROCESS RISK CALCULATION
# =====================================================
def calculate_risk(name, exe_path, connection_count, whitelisted):
    score = 0
    reasons = []

    if name in SYSTEM_PROCESS_ALLOWLIST:
        return 0, []

    unusual_path = exe_path and is_suspicious_path(exe_path)

    if unusual_path:
        score += 30
        reasons.append("Unusual executable location")

    if unusual_path and not whitelisted:
        score += 20
        reasons.append("Not in whitelist")

    if connection_count > 5:
        score += 15
        reasons.append("High outbound activity")

    if exe_path and any(x in exe_path.lower() for x in ["temp", "downloads"]):
        score += 25
        reasons.append("Running from temp/downloads")

    return score, reasons


# =====================================================
# STARTUP REGISTRY SCAN
# =====================================================
def scan_startup_registry():
    entries = []
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
                        entries.append(f"{name} → {value}")
                        i += 1
                    except OSError:
                        break
        except FileNotFoundError:
            continue

    return entries


def analyze_startup_entry(entry_text):
    score = 0
    reasons = []
    lower = entry_text.lower()

    if "temp" in lower or "downloads" in lower:
        score += 40
        reasons.append("Startup entry running from temp/downloads")

    if ".exe" in lower and "appdata" in lower:
        score += 10
        reasons.append("User-level startup executable")

    return score, reasons


# =====================================================
# SCHEDULED TASK SCAN
# =====================================================
def scan_scheduled_tasks():
    tasks = []

    try:
        result = subprocess.run(
            ["schtasks", "/Query", "/FO", "LIST", "/V"],
            capture_output=True,
            text=True
        )

        blocks = result.stdout.split("\n\n")

        for block in blocks:
            name = None
            action = None

            for line in block.splitlines():
                if line.startswith("TaskName:"):
                    name = line.replace("TaskName:", "").strip()
                if line.startswith("Task To Run:"):
                    action = line.replace("Task To Run:", "").strip()

            if name:
                tasks.append({"name": name, "action": action})

    except:
        tasks.append({"name": "Error retrieving tasks", "action": None})

    return tasks


def analyze_scheduled_task(task):
    score = 0
    reasons = []

    action = task.get("action") or ""
    lower = action.lower()

    if not action:
        return 0, []

    if "temp" in lower or "downloads" in lower:
        score += 40
        reasons.append("Scheduled task runs from temp/downloads")

    if ".exe" in lower and "appdata" in lower:
        score += 10
        reasons.append("User-level executable in scheduled task")

    if not any(safe in action for safe in SAFE_PATHS):
        score += 20
        reasons.append("Task executable outside safe paths")

    return score, reasons


# =====================================================
# WINDOWS SERVICES (psutil version)
# =====================================================
def scan_windows_services():
    services = []

    try:
        for service in psutil.win_service_iter():
            try:
                info = service.as_dict()
                services.append({
                    "name": info.get("name"),
                    "status": info.get("status"),
                    "binpath": info.get("binpath")
                })
            except:
                continue
    except:
        services.append({
            "name": "Error retrieving services",
            "status": "unknown",
            "binpath": None
        })

    return services


def analyze_service(service):
    score = 0
    reasons = []

    binpath = service.get("binpath") or ""
    lower_path = binpath.lower()

    if "temp" in lower_path or "downloads" in lower_path:
        score += 40
        reasons.append("Service running from temp/downloads")

    if binpath and not any(safe in binpath for safe in SAFE_PATHS):
        score += 20
        reasons.append("Service executable outside safe paths")

    return score, reasons


# =====================================================
# DISK SPIKE DETECTION
# =====================================================
write_history = {}
spike_counter = {}

def detect_high_disk_activity():
    global write_history, spike_counter

    highest_delta = 0
    suspect_name = None

    for proc in psutil.process_iter(['pid', 'name']):
        try:
            io = proc.io_counters()
            current_write = io.write_bytes
            pid = proc.pid

            if pid in write_history:
                delta = current_write - write_history[pid]

                if delta > highest_delta:
                    highest_delta = delta
                    suspect_name = proc.name()

                if delta > 50_000:
                    spike_counter[pid] = spike_counter.get(pid, 0) + 1
                else:
                    spike_counter[pid] = 0

            write_history[pid] = current_write

        except:
            continue

    if highest_delta > 50_000:
     return suspect_name, highest_delta

    return None, 0



# =====================================================
# THREAT SUMMARY
# =====================================================
def generate_threat_summary(highest_score):
    if highest_score == 0:
        return "System appears healthy. No significant threats detected."
    if highest_score <= 20:
        return "Low-risk indicators detected. No immediate action required."
    if highest_score <= 50:
        return "Moderate risk detected. Review recommended."
    if highest_score <= 80:
        return "High risk detected. Immediate investigation advised."
    return "Critical threat level detected. Immediate action required."


# =====================================================
# MAIN SECURITY ENGINE
# =====================================================
def scan_system():

    report = []
    highest_score = 0
    suspected_process = None

    whitelist = load_whitelist()
    mode = get_mode()

    # PROCESS ENUMERATION
    processes = list(psutil.process_iter(['pid', 'name', 'exe']))
    report.append(f"Running processes: {len(processes)}")

    # NETWORK ANALYSIS
    connections = psutil.net_connections(kind='inet')
    process_connections = defaultdict(int)

    for conn in connections:
        if conn.raddr and conn.pid:
            try:
                process = psutil.Process(conn.pid)
                process_connections[process.name()] += 1
            except:
                pass

    total_outbound = sum(process_connections.values())
    report.append(f"Active outbound connections: {total_outbound}")

    if process_connections:
        sorted_procs = sorted(process_connections.items(), key=lambda x: x[1], reverse=True)
        report.append("Top network-active processes:")
        for name, count in sorted_procs[:5]:
            report.append(f" - {name}: {count} connections")

    # PROCESS RISK ANALYSIS
    report.append("\nRisk Analysis:")

    for name, count in process_connections.items():
        try:
            proc = next(p for p in processes if p.info['name'] == name)
            exe_path = proc.info['exe']
        except:
            exe_path = None

        whitelisted = exe_path in whitelist["approved_paths"] if exe_path else False
        score, reasons = calculate_risk(name, exe_path, count, whitelisted)

        if score > highest_score:
            highest_score = score

        if score > 0:
            level = "LOW" if score <= 20 else "MEDIUM" if score <= 50 else "HIGH" if score <= 80 else "CRITICAL"
            report.append(f"\n{name} → Risk Score: {score} ({level})")
            for r in reasons:
                report.append(f"   - {r}")

    # -----------------------------------------
    # DISK BEHAVIOR CHECK (Independent of burst)
    # -----------------------------------------

    suspected_process = None

    process_name, write_bytes = detect_high_disk_activity()

    if process_name:
      suspected_process = process_name
      highest_score = max(highest_score, 70)

      report.append("\nDisk Activity Analysis:")
      report.append(" Risk Score: 70 (HIGH)")
      report.append(
        f"  - Sustained abnormal disk writer detected: {process_name} ({write_bytes} bytes)"
    )

    # -----------------------------------------
    # FOLDER BURST CHECK (Separate signal)
    # -----------------------------------------

    folder_score, folder_reasons = get_folder_risk()

    if folder_score > 0:
     report.append("\nSensitive Folder Activity:")
     for r in folder_reasons:
        report.append(f"  - {r}")

    # STARTUP CHECK
    report.append("\nStartup Registry Entries:")
    for entry in scan_startup_registry():
        report.append(f" - {entry}")

    # SCHEDULED TASKS
    report.append("\nScheduled Tasks:")
    for task in scan_scheduled_tasks()[:10]:
        report.append(f" - {task['name']}")

    # SERVICES
    report.append("\nWindows Services:")
    for svc in scan_windows_services()[:20]:
        report.append(f" - {svc.get('name')} ({svc.get('status')})")

    # FINAL SUMMARY
    report.append("\nThreat Summary:")
    report.append(generate_threat_summary(highest_score))

    return {
        "report": "\n".join(report),
        "suspect": suspected_process
    }
