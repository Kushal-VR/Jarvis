CURRENT_MODE = "PASSIVE"

def set_mode(mode):
    global CURRENT_MODE
    CURRENT_MODE = mode.upper()
    return f"Defense mode set to {CURRENT_MODE}"

def get_mode():
    return CURRENT_MODE
