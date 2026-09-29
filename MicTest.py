import sounddevice as sd
from faster_whisper import WhisperModel

# find the ReSpeaker in the list of audio devices
dev = next(i for i, d in enumerate(sd.query_devices())
           if "ReSpeaker" in d["name"] and d["max_input_channels"] > 0)
chans = sd.query_devices(dev)["max_input_channels"]
print("channels:", chans)  # 1 or 6 tells you which firmware it's on

# record 5 seconds at 16kHz from all channels
audio = sd.rec(5 * 16000, samplerate=16000, channels=chans, device=dev, dtype="float32")
sd.wait()

mono = audio[:, 0]  # channel 0 = the cleaned-up audio

model = WhisperModel("base", compute_type="int8")
segments, _ = model.transcribe(mono)
print(" ".join(s.text for s in segments))