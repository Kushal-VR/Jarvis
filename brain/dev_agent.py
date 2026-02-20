import os

# =====================================================
# READ FILE CONTENT
# =====================================================
def read_file(path: str):
    """
    Reads a file safely
    """
    try:
        if not os.path.exists(path):
            return "File not found."

        # limit size (prevent huge file crash)
        if os.path.getsize(path) > 200000:
            return "File too large to read."

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        return f"📄 File: {path}\n\n{content}"

    except Exception as e:
        return f"Error reading file: {str(e)}"
