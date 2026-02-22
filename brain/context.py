# =====================================================
# CONTEXT MEMORY (SHORT-TERM SESSION MEMORY)
# =====================================================

last_results = None


def store_results(results):
    global last_results
    last_results = results


def get_last_results():
    return last_results


def clear_context():
    global last_results
    last_results = None