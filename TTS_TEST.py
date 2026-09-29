import asyncio
import edge_tts
import os

VOICE = "en-US-AriaNeural"  # clear, natural US English voice

async def speak(text, filename="output.mp3"):
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(filename)
    os.system(f"start {filename}" if os.name == "nt" else f"afplay {filename}")

if __name__ == "__main__":
    asyncio.run(speak("Turn left in fifty feet to reach the food court."))