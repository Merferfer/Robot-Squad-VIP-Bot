import sounddevice as sd
import numpy as np
import threading
import asyncio
import queue
import io
import re
import time
import difflib
import requests
import edge_tts
import pygame
from faster_whisper import WhisperModel
from stores import STORES
from Ollama import stream_llm_response

SAMPLE_RATE = 16000
VOICE = "en-US-AriaNeural"
STOPWORDS = {"a", "the", "and", "of", "at", "to", "in"}
NAV_PHRASES = ["take me to", "i want to go to", "where is", "go to"]
MAX_HISTORY = 6  # last 3 back-and-forths

model = WhisperModel("base.en", device="cpu", compute_type="int8")
pygame.mixer.init()
conversation_history = []


def warm_up_ollama():
    # empty request just loads the model into memory so the first real question isn't slow
    try:
        requests.post("http://localhost:11434/api/generate",
                      json={"model": "llama3.2", "keep_alive": "30m"}, timeout=60)
    except requests.RequestException:
        print("Couldn't reach Ollama, is it running?")


def record_until_enter():
    print("\nPress Enter to start recording...")
    input()
    print("Recording... press Enter again to stop.")

    frames = []
    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    stream.start()

    stop_event = threading.Event()
    def wait_for_enter():
        input()
        stop_event.set()

    listener = threading.Thread(target=wait_for_enter, daemon=True)
    listener.start()

    while not stop_event.is_set():
        data, _ = stream.read(1024)
        frames.append(data.copy())

    stream.stop()
    stream.close()
    listener.join(timeout=0.1)
    return np.concatenate(frames, axis=0).flatten()


def transcribe(audio):
    segments, _ = model.transcribe(audio, language="en", beam_size=1, vad_filter=True)
    return " ".join(seg.text for seg in segments).strip()


# ---------- TTS ----------

async def synth(text):
    # grab edge-tts audio straight into memory instead of saving an mp3
    buf = io.BytesIO()
    async for chunk in edge_tts.Communicate(text, VOICE).stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    buf.seek(0)
    return buf


async def wait_for_playback():
    while pygame.mixer.music.get_busy():
        await asyncio.sleep(0.02)


async def speak_queue(q):
    # takes sentences off the queue one at a time;
    # makes audio for the next sentence while the current one is still playing
    current = None
    while True:
        sentence = await asyncio.to_thread(q.get)
        if sentence is None:
            break
        next_audio = await synth(sentence)
        await wait_for_playback()
        current = next_audio  # keep a reference so it isn't deleted mid-play
        pygame.mixer.music.load(current, "mp3")
        pygame.mixer.music.play()
    await wait_for_playback()


# ---------- store matching (same as before) ----------

def find_store(spoken_text):
    text = spoken_text.lower()

    for store in STORES:
        if store.lower().replace("'", "") in text:
            return store

    text_words = set(re.findall(r"\w+", text))
    for store in STORES:
        words = [w for w in store.lower().replace("'", "").split() if w not in STOPWORDS and len(w) > 2]
        if words and all(w in text_words for w in words):
            return store

    matches = difflib.get_close_matches(text, [s.lower() for s in STORES], n=1, cutoff=0.6)
    if matches:
        for store in STORES:
            if store.lower() == matches[0]:
                return store
    return None


def navigate_to(store_name):
    """Placeholder hook for the navigation sub-team."""
    print(f"[NAV STUB] Would now navigate to: {store_name}")


# ---------- LLM ----------

def remember(user_text, reply):
    conversation_history.append({"role": "user", "content": user_text})
    conversation_history.append({"role": "assistant", "content": reply})
    del conversation_history[:-MAX_HISTORY]  # toss old turns


def llm_to_sentences(user_text, q):
    # runs in the background: chops Llama's streamed answer into sentences and queues them up
    buffer, full = "", ""
    try:
        for token in stream_llm_response(user_text, conversation_history):
            buffer += token
            full += token
            while True:
                m = re.search(r"[.!?]\s", buffer)
                if not m:
                    break
                sentence = buffer[:m.end()].strip()
                buffer = buffer[m.end():]
                if sentence:
                    q.put(sentence)
        if buffer.strip():
            q.put(buffer.strip())
        remember(user_text, full.strip())
    except Exception as e:
        print(f"LLM error: {e}")
        q.put("Sorry, I had trouble with that. Could you try again?")
    finally:
        q.put(None)  # tells the speaker it's done, even if something broke


def handle(user_text):
    q = queue.Queue()
    store = find_store(user_text)

    if store:
        navigate_to(store)
        q.put(f"Going to {store}.")
        q.put(None)
    elif any(p in user_text.lower() for p in NAV_PHRASES):
        q.put("Sorry, I didn't recognize that store. Could you say it again?")
        q.put(None)
    else:
        threading.Thread(target=llm_to_sentences, args=(user_text, q), daemon=True).start()
    return q


def main():
    warm_up_ollama()
    print("Voice loop running. Ctrl+C to quit.")
    while True:
        audio = record_until_enter()

        t0 = time.perf_counter()
        heard = transcribe(audio)
        print(f"You said: {heard}  ({time.perf_counter() - t0:.2f}s to transcribe)")

        if not heard:
            print("Didn't catch anything, try again.")
            continue

        asyncio.run(speak_queue(handle(heard)))


if __name__ == "__main__":
    main()