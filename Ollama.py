import json
import requests
from stores import STORES

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "llama3.2"   # later you can try "llama3.2:1b" here for faster (but dumber) answers

# turns your store list into one comma-separated line the model can read
store_list = ", ".join(STORES)

SYSTEM_PROMPT = f"""You are a friendly guide robot in a shopping mall. You help blind and visually impaired visitors get around.

Rules:
- Keep every answer to 1-2 short sentences. People are listening, not reading.
- Speak plainly. No lists, no emojis, no markdown, no symbols, since everything you say is read out loud.
- Never mention colors, signs, or anything the person would have to see.
- Only talk about stores from this list. If someone asks about a store not on it, say the mall doesn't have it.
- If someone wants to go to a store, tell them to say "take me to" and the store name.
- If you don't know something, say so instead of guessing.

Stores in this mall: {store_list}
"""

# one shared set of options so the warm-up and the real questions match exactly
OPTIONS = {"num_predict": 100, "num_ctx": 2048}


def warm_up():
    # sends a tiny real request so the model AND the system prompt are already processed
    try:
        payload = {
            "model": MODEL,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": "hi"}],
            "stream": False,
            "keep_alive": "30m",
            "options": {**OPTIONS, "num_predict": 1},  # only need one token out
        }
        requests.post(OLLAMA_URL, json=payload, timeout=120)
    except requests.RequestException:
        print("Couldn't reach Ollama, is it running?")


def stream_llm_response(user_text, history):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [{"role": "user", "content": user_text}]
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": True,          # send words back as they're generated
        "keep_alive": "30m",     # keep the model loaded between questions
        "options": OPTIONS,
    }
    with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=120) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            yield data.get("message", {}).get("content", "")
            if data.get("done"):
                break