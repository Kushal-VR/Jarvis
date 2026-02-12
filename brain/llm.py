import requests
from brain.memory import add_permanent_memory, add_temporary_memory, get_all_memory

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:3b"

SYSTEM_PROMPT = """
You are Jarvis, a professional personal AI assistant.
Only remember information when the user explicitly says:
"remember this" or "store this permanently".
Do not store random conversation.
"""

conversation_history = []


def ask_llm(prompt: str) -> str:
    global conversation_history

    # Check for memory command
    lower_prompt = prompt.lower()

    # Permanent memory triggers
    if lower_prompt.startswith("remember") or "store permanently" in lower_prompt:
     content = prompt.replace("remember", "").replace("store permanently", "").strip()
     add_permanent_memory(content)
     return "Memory stored permanently."

    # Temporary memory trigger
    if lower_prompt.startswith("store temporarily"):
       content = prompt.replace("store temporarily", "").strip()
       add_temporary_memory(content)
       return "Temporary memory stored for 30 days."


    conversation_history.append(f"User: {prompt}")

    memory_context = "\n".join(get_all_memory())

    full_prompt = SYSTEM_PROMPT + "\n\nStored Memory:\n" + memory_context + "\n\n" + "\n".join(conversation_history) + "\nJarvis:"

    payload = {
        "model": MODEL_NAME,
        "prompt": full_prompt,
        "stream": False,
    }

    response = requests.post(OLLAMA_URL, json=payload, timeout=120)
    response.raise_for_status()

    data = response.json()
    reply = data["response"].strip()

    conversation_history.append(f"Jarvis: {reply}")

    return reply
