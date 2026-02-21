import os


def read_file(path: str):
    """
    Reads file safely without random cut
    """

    try:
        if not os.path.exists(path):
            return "File not found."

        # 🔥 increase limit (IMPORTANT)
        if os.path.getsize(path) > 500000:
            return "File too large to display fully."

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        # 🔥 DO NOT CUT randomly
        return f"📄 Reading file: {path}\n\n{content}"

    except Exception as e:
        return f"Error reading file: {str(e)}"