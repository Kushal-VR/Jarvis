import psutil
from collections import defaultdict
import json
import winreg
import subprocess
import time

from guardian.mode import get_mode
from guardian.folder_monitor import get_folder_risk


# =====================================================
# SYSTEM ALLOWLIST
# Trusted processes ignored in risk scoring
# =====================================================
SYSTEM_PROCESS_ALLOWLIST = [
    "svchost.exe",
    "WUDFHost.exe",
    "SystemSettings.exe",
    "NVDisplay.Container.exe",
    "ipfsvc.exe",
    "Code.exe",
    "python.exe",
]

# =====================================================
# SAFE EXECUTION PATHS
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
    import psutil
    import time

    terminated = False

    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] == name:

                # Step 1: Try graceful terminate
                proc.terminate()

                try:
                    proc.wait(timeout=2)
                    terminated = True
                except psutil.TimeoutExpired:
                    # Step 2: Force kill if not closed
                    proc.kill()
                    terminated = True

        except Exception:
            continue

    if terminated:
        return f"Process {name} terminated successfully."
    else:
        return f"Process {name} not found."

# =====================================================
# PATH CHECKER
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
        r"Software\\Microsoft\\Windows\\CurrentVersion\\Run",
        r"Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce"
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

            for line in block.splitlines():
                if line.startswith("TaskName:"):
                    name = line.replace("TaskName:", "").strip()

            if name:
                tasks.append({"name": name})

    except:
        tasks.append({"name": "Error retrieving tasks"})

    return tasks


# =====================================================
# WINDOWS SERVICE SCAN
# =====================================================
def scan_windows_services():
    services = []

    try:
        for service in psutil.win_service_iter():
            info = service.as_dict()
            services.append({
                "name": info.get("name"),
                "status": info.get("status"),
            })
    except:
        services.append({"name": "Error", "status": "unknown"})

    return services


# =====================================================
# DISK SPIKE TUNING (v2)
# =====================================================
write_history = {}
spike_counter = {}
write_baseline = {}

last_alert_time = 0

DISK_ALERT_COOLDOWN = 60
SPIKE_THRESHOLD = 2_000_000
REQUIRED_SPIKES = 3

TRUSTED_DISK_WRITERS = [
    "svchost.exe",
    "explorer.exe",
    "Code.exe",
    "python.exe"
]


def detect_high_disk_activity():
    """
    Advanced disk anomaly detection:
    - cooldown
    - rolling baseline
    - sustained spikes
    """

    global write_history, spike_counter
    global write_baseline, last_alert_time

    now = time.time()

    # cooldown
    if now - last_alert_time < DISK_ALERT_COOLDOWN:
        return None, 0

    highest_delta = 0
    suspect_name = None

    for proc in psutil.process_iter(['pid', 'name']):
        try:
            name = proc.info['name']

            if name in TRUSTED_DISK_WRITERS:
                continue

            io = proc.io_counters()
            current_write = io.write_bytes
            pid = proc.pid

            if pid in write_history:
                delta = current_write - write_history[pid]

                old_avg = write_baseline.get(pid, delta)
                new_avg = (old_avg * 0.7) + (delta * 0.3)
                write_baseline[pid] = new_avg

                if delta > max(SPIKE_THRESHOLD, new_avg * 4):
                    spike_counter[pid] = spike_counter.get(pid, 0) + 1

                    if delta > highest_delta:
                        highest_delta = delta
                        suspect_name = name
                else:
                    spike_counter[pid] = max(spike_counter.get(pid, 0) - 1, 0)

            write_history[pid] = current_write

        except:
            continue

    if suspect_name:
        for pid, count in spike_counter.items():
            if count >= REQUIRED_SPIKES:
                last_alert_time = now
                return suspect_name, highest_delta

    return None, 0


# =====================================================
# THREAT SUMMARY
# =====================================================
def generate_threat_summary(score):
    if score == 0:
        return "System appears healthy. No significant threats detected."
    if score <= 20:
        return "Low-risk indicators detected."
    if score <= 50:
        return "Moderate risk detected."
    if score <= 80:
        return "High risk detected. Immediate investigation advised."
    return "Critical threat level detected."


# =====================================================
# MAIN SECURITY ENGINE
# =====================================================
def scan_system():

    report = []
    highest_score = 0
    suspected_process = None

    whitelist = load_whitelist()

    processes = list(psutil.process_iter(['pid', 'name', 'exe']))
    report.append(f"Running processes: {len(processes)}")

    connections = psutil.net_connections(kind='inet')
    process_connections = defaultdict(int)

    for conn in connections:
        if conn.raddr and conn.pid:
            try:
                process_connections[psutil.Process(conn.pid).name()] += 1
            except:
                pass

    report.append(f"Active outbound connections: {sum(process_connections.values())}")

    report.append("Top network-active processes:")
    for name, count in sorted(process_connections.items(), key=lambda x: x[1], reverse=True)[:5]:
        report.append(f" - {name}: {count} connections")

    report.append("\nRisk Analysis:")

    for name, count in process_connections.items():
        exe_path = None
        try:
            proc = next(p for p in processes if p.info['name'] == name)
            exe_path = proc.info['exe']
        except:
            pass

        whitelisted = exe_path in whitelist["approved_paths"] if exe_path else False
        score, reasons = calculate_risk(name, exe_path, count, whitelisted)

        highest_score = max(highest_score, score)

        if score > 0:
            report.append(f"\n{name} → Risk Score: {score}")
            for r in reasons:
                report.append(f"   - {r}")

    # DISK ANALYSIS
    proc_name, bytes_written = detect_high_disk_activity()

    if proc_name:
        suspected_process = proc_name
        highest_score = max(highest_score, 70)

        report.append("\nDisk Activity Analysis:")
        report.append(" Risk Score: 70 (HIGH)")
        report.append(f"  - Sustained abnormal disk writer: {proc_name} ({bytes_written} bytes)")

    # Folder risk
    folder_score, folder_reasons = get_folder_risk()
    if folder_score > 0:
        report.append("\nSensitive Folder Activity:")
        for r in folder_reasons:
            report.append(f"  - {r}")

    report.append("\nStartup Registry Entries:")
    for e in scan_startup_registry():
        report.append(f" - {e}")

    report.append("\nScheduled Tasks:")
    for t in scan_scheduled_tasks()[:10]:
        report.append(f" - {t['name']}")

    report.append("\nWindows Services:")
    for s in scan_windows_services()[:20]:
        report.append(f" - {s['name']} ({s['status']})")

    report.append("\nThreat Summary:")
    report.append(generate_threat_summary(highest_score))

    return {
        "report": "\n".join(report),
        "suspect": suspected_process
    }
