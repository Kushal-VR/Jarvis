import os

def get_disk_usage(path="C:\\"):
    total_size = 0

    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            try:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
            except:
                continue

    return total_size


def format_size(bytes_size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024


def scan_large_files(path="C:\\", limit=10):
    files = []

    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            try:
                fp = os.path.join(dirpath, f)
                size = os.path.getsize(fp)
                files.append((fp, size))
            except:
                continue

    files.sort(key=lambda x: x[1], reverse=True)

    top_files = files[:limit]

    result = "Top Large Files:\n"
    for f, s in top_files:
        result += f"{format_size(s)} → {f}\n"

    return result