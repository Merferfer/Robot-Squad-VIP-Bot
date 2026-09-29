import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel

SAMPLE_RATE = 16000

# "base" is a good balance of speed/accuracy for a laptop.
# use "tiny" if it feels slow, "small" if you want better accuracy.
model = WhisperModel("base", device="cpu", compute_type="int8")

def record_until_enter():
    print("Press Enter to start recording...")
    input()
    print("Recording... press Enter again to stop.")

    frames = []
    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    stream.start()

    import threading
    stop_flag = {"stop": False}
    def wait_for_enter():
        input()
        stop_flag["stop"] = True
    threading.Thread(target=wait_for_enter, daemon=True).start()

    while not stop_flag["stop"]:
        data, _ = stream.read(1024)
        frames.append(data.copy())

    stream.stop()
    stream.close()
    return np.concatenate(frames, axis=0).flatten()

def transcribe(audio):
    segments, _ = model.transcribe(audio, language="en")
    text = " ".join(seg.text for seg in segments).strip()
    return text

if __name__ == "__main__":
    audio = record_until_enter()
    print("Transcribing...")
    result = transcribe(audio)
    print(f"You said: {result}")