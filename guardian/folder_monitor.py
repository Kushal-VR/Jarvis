import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Sensitive folders
SENSITIVE_FOLDERS = [
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Documents"),
    os.path.expanduser("~/Downloads"),
]

EVENT_WINDOW_SECONDS = 10
BURST_THRESHOLD = 25
ALERT_COOLDOWN = 20

event_timestamps = []
burst_detected = False
last_alert_time = 0


class SensitiveFolderHandler(FileSystemEventHandler):

    def on_modified(self, event):
        if not event.is_directory:
            handle_event()

    def on_created(self, event):
        if not event.is_directory:
            handle_event()

    def on_deleted(self, event):
        if not event.is_directory:
            handle_event()


def handle_event():
    global event_timestamps, burst_detected, last_alert_time

    current_time = time.time()
    event_timestamps.append(current_time)

    # Keep recent timestamps
    event_timestamps[:] = [
        t for t in event_timestamps
        if current_time - t < EVENT_WINDOW_SECONDS
    ]

    if len(event_timestamps) >= BURST_THRESHOLD:
        if current_time - last_alert_time > ALERT_COOLDOWN:
            burst_detected = True
            last_alert_time = current_time

            print("\n⚠ FILE BURST ALERT: High file activity detected.\n")


def get_folder_risk():
    global burst_detected

    if burst_detected:
        burst_detected = False
        return 70, ["Mass file activity detected in sensitive folders"]

    return 0, []


def start_folder_monitor():
    observer = Observer()
    handler = SensitiveFolderHandler()

    for folder in SENSITIVE_FOLDERS:
        if os.path.exists(folder):
            observer.schedule(handler, folder, recursive=True)

    observer.start()
    print("📂 Folder monitor active (Desktop/Documents/Downloads).")

    return observer
