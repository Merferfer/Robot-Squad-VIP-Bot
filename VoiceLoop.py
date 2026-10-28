import sounddevice as sd
import numpy as np
import threading
import asyncio
import queue
import io
import re
import time
import difflib
import collections
import requests
import edge_tts
import pygame
from pygame._sdl2 import audio as sdl_audio
from faster_whisper import WhisperModel
from stores import STORES
from Ollama import stream_llm_response

# ---------- settings ----------

SAMPLE_RATE = 16000
BLOCK = 1024            # about 64 ms of audio per chunk at 16 kHz
SPEECH_MARGIN = 3.0     # how many times louder than room noise counts as "talking"
SILENCE_END = 0.8       # seconds of quiet that means you're done talking
MIN_SPEECH = 0.4        # ignore blips shorter than this (door slams, coughs)
MAX_SPEECH = 15         # safety cutoff in seconds
POST_SPEAK_WAIT = 0.4   # wait after the robot stops talking so room echo dies down

VOICE = "en-US-AriaNeural"
STOPWORDS = {"a", "the", "and", "of", "at", "to", "in"}
NAV_PHRASES = ["take me to", "i want to go to", "where is", "go to"]
MAX_HISTORY = 6         # last 3 back-and-forths
MIC_NAME = "ReSpeaker"  # part of the device name; used to find the mic array

mic_queue = queue.Queue()
speaking = threading.Event()   # on while the robot is talking
TIMING = {}                    # temporary: used for the [timing] prints
conversation_history = []

model = WhisperModel("base.en", device="cpu", compute_type="int8")


# ---------- ReSpeaker setup ----------

def find_mic():
    # looks through all audio devices for the ReSpeaker (falls back to system default)
    for i, d in enumerate(sd.query_devices()):
        if MIC_NAME.lower() in d["name"].lower() and d["max_input_channels"] > 0:
            return i, d["max_input_channels"], d["name"]
    return None, 1, None


MIC_INDEX, MIC_CHANNELS, mic_name = find_mic()
speaker_name = None  # use the Windows default output (the USB speaker for now)
print(f"Mic: {mic_name or 'system default (ReSpeaker not found)'} ({MIC_CHANNELS} ch)")
print(f"Speaker: {speaker_name or 'system default'}")

if speaker_name:
    pygame.mixer.init(devicename=speaker_name)
else:
    pygame.mixer.init()


def warm_up_ollama():
    # empty request just loads the model into memory so the first real question isn't slow
    try:
        requests.post("http://localhost:11434/api/generate",
                      json={"model": "llama3.2", "keep_alive": "30m"}, timeout=60)
    except requests.RequestException:
        print("Couldn't reach Ollama, is it running?")


# ---------- listening ----------

def mic_reader():
    # runs in the background: reads the mic nonstop and feeds the queue
    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=MIC_CHANNELS,
                            dtype="float32", device=MIC_INDEX)
    stream.start()
    while True:
        data, _ = stream.read(BLOCK)
        if speaking.is_set():
            continue  # robot is talking, read it but throw it away
        mic_queue.put(data[:, 0].copy())  # channel 0 = cleaned-up audio


def start_mic():
    threading.Thread(target=mic_reader, daemon=True).start()


def calibrate(seconds=1.5):
    # measures the room's background noise so "talking" is judged relative to it
    print("Measuring room noise, stay quiet...")
    levels = []
    end = time.time() + seconds
    while time.time() < end:
        block = mic_queue.get()
        levels.append(np.sqrt(np.mean(block ** 2)))
    ambient = float(np.median(levels))
    threshold = max(ambient * SPEECH_MARGIN, 0.003)
    print(f"Room noise: {ambient:.5f}, speech threshold: {threshold:.5f}")
    return threshold


def listen_for_utterance(threshold):
    # waits until you start talking, records until you go quiet, returns the audio
    pre = collections.deque(maxlen=10)  # a little audio from before you start, so the first word isn't clipped
    frames, talking, quiet_blocks = [], False, 0
    block_sec = BLOCK / SAMPLE_RATE

    while True:
        block = mic_queue.get()
        loud = np.sqrt(np.mean(block ** 2)) > threshold

        if not talking:
            pre.append(block)
            if loud:
                talking = True
                frames = list(pre)
                quiet_blocks = 0
        else:
            frames.append(block)
            quiet_blocks = 0 if loud else quiet_blocks + 1
            total = len(frames) * block_sec
            if quiet_blocks * block_sec >= SILENCE_END or total >= MAX_SPEECH:
                if total - SILENCE_END >= MIN_SPEECH:
                    return np.concatenate(frames)
                talking, frames = False, []  # too short, was just noise
                pre.clear()


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
        if not TIMING.get("played", True):
            print(f"[timing] audio starts: {time.perf_counter() - TIMING['t']:.2f}s")
            TIMING["played"] = True
    await wait_for_playback()


# ---------- store matching ----------

def clean(s):
    # lowercase, drop apostrophes, turn other punctuation into spaces
    s = s.lower().replace("'", "").replace("’", "")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def find_store(spoken_text):
    text = clean(spoken_text)

    # 1. store name appears directly in the sentence
    for store in STORES:
        if clean(store) in text:
            return store

    # 2. every important word of the store name appears
    text_words = set(text.split())
    for store in STORES:
        words = [w for w in clean(store).split() if w not in STOPWORDS and len(w) > 2]
        if words and all(w in text_words for w in words):
            return store

    # 3. fuzzy match: cut off "take me to" etc. first, then compare what's left
    for p in NAV_PHRASES:
        text = text.replace(clean(p), "")
    text = text.strip()
    lookup = {clean(s): s for s in STORES}
    matches = difflib.get_close_matches(text, list(lookup), n=1, cutoff=0.6)
    return lookup[matches[0]] if matches else None


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
    first = True
    try:
        for token in stream_llm_response(user_text, conversation_history):
            if first:
                print(f"[timing] first token: {time.perf_counter() - TIMING['t']:.2f}s")
                first = False
            buffer += token
            full += token
            while True:
                m = re.search(r"[.!?]\s", buffer)
                if not m:
                    break
                sentence = buffer[:m.end()].strip()
                buffer = buffer[m.end():]
                if sentence:
                    if not TIMING["sent"]:
                        print(f"[timing] first sentence ready: {time.perf_counter() - TIMING['t']:.2f}s")
                        TIMING["sent"] = True
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


# ---------- main loop ----------

def main():
    warm_up_ollama()
    start_mic()
    threshold = calibrate()
    print("Listening... (Ctrl+C to quit)")
    while True:
        audio = listen_for_utterance(threshold)

        t0 = time.perf_counter()
        heard = transcribe(audio)
        print(f"You said: {heard}  ({time.perf_counter() - t0:.2f}s to transcribe)")

        if not heard:
            continue

        TIMING.update(t=time.perf_counter(), sent=False, played=False)

        speaking.set()  # mic ignores everything while the robot talks
        try:
            asyncio.run(speak_queue(handle(heard)))
        finally:
            time.sleep(POST_SPEAK_WAIT)          # let the echo die down
            while not mic_queue.empty():         # dump anything left in the buffer
                mic_queue.get_nowait()
            speaking.clear()


if __name__ == "__main__":
    main()