def summarize_list(items):
    """
    Convert list into readable format
    """

    if not items:
        return "No results found."

    output = "Here are the results:\n\n"

    for i, item in enumerate(items, 1):
        output += f"{i}. {item}\n"

    return output.strip()