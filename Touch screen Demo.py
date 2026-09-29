import asyncio
import os
import tempfile
import threading
import uuid

import pygame
import edge_tts

from kivy.app import App
from kivy.uix.gridlayout import GridLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.core.window import Window
from kivy.clock import Clock

pygame.mixer.init()

DESTINATIONS = [
    {"label": "Restrooms", "say": "Navigating to the nearest restrooms."},
    {"label": "Food Court", "say": "Taking you to the food court."},
    {"label": "Store Directory", "say": "Let's find your store in the directory."},
    {"label": "Seating Area", "say": "Heading to the nearest seating area."},
    {"label": "Help Desk", "say": "Taking you to the help desk."},
    {"label": "Exit / Parking", "say": "Guiding you to the nearest exit."},
]

VOICE = "en-US-AriaNeural"
ARRIVAL_DELAY_SECONDS = 5  # how long the fake "walk there" takes


def speak(text):
    """Generate TTS with edge-tts, play it with pygame. Runs in a background
    thread so the UI doesn't freeze while the audio file is being generated."""
    def _run():
        async def _gen():
            # Unique filename per call — reusing one file causes it to still
            # be locked/open by pygame from the previous playback, so the
            # second and later calls fail silently to overwrite it.
            tmp_path = os.path.join(
                tempfile.gettempdir(), f"wayfinder_tts_{uuid.uuid4().hex}.mp3"
            )
            communicate = edge_tts.Communicate(text, VOICE)
            await communicate.save(tmp_path)
            return tmp_path

        try:
            tmp_path = asyncio.run(_gen())
            pygame.mixer.music.stop()
            try:
                pygame.mixer.music.unload()  # release the previous file, if any (pygame 2.0+)
            except AttributeError:
                pass  # older pygame versions don't have unload(); stop() is enough
            pygame.mixer.music.load(tmp_path)
            pygame.mixer.music.play()
        except Exception as e:
            # Without this, a failure here just dies silently in the thread
            # and you'd have no idea why the voice stopped working.
            print(f"[speak] TTS/playback failed: {e}")

    threading.Thread(target=_run, daemon=True).start()


class HomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation="vertical", padding=20, spacing=20)

        title = Label(text="Where would you like to go?", font_size="24sp", size_hint=(1, 0.15))
        layout.add_widget(title)

        grid = GridLayout(cols=3, spacing=20)
        for dest in DESTINATIONS:
            btn = Button(text=dest["label"], font_size="20sp")
            btn.bind(on_press=lambda inst, d=dest: self.select_destination(d))
            grid.add_widget(btn)

        layout.add_widget(grid)
        self.add_widget(layout)

    def select_destination(self, dest):
        speak(dest["say"])
        self.manager.get_screen("nav").set_destination(dest)
        self.manager.current = "nav"


class NavScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation="vertical", padding=40, spacing=20)
        self.title_label = Label(text="Heading to...", font_size="28sp")
        self.sub_label = Label(text="Follow the path. I'll let you know when we arrive.", font_size="16sp")
        cancel_btn = Button(text="Cancel", size_hint=(1, 0.2), font_size="18sp")
        cancel_btn.bind(on_press=self.cancel)

        layout.add_widget(self.title_label)
        layout.add_widget(self.sub_label)
        layout.add_widget(cancel_btn)
        self.add_widget(layout)

        self._arrival_event = None  # so we can cancel it if the user hits Cancel

    def set_destination(self, dest):
        self.title_label.text = f"Heading to {dest['label']}"
        self.sub_label.text = "Follow the path. I'll let you know when we arrive."

        # Kick off the fake "walking there" timer. Clock.schedule_once runs
        # on Kivy's own clock, so it plays nicely with the UI thread (unlike
        # time.sleep, which would freeze the whole app).
        if self._arrival_event:
            self._arrival_event.cancel()
        self._arrival_event = Clock.schedule_once(
            lambda dt: self.arrive(dest), ARRIVAL_DELAY_SECONDS
        )

    def arrive(self, dest):
        speak(f"You've arrived at {dest['label']}.")
        self.manager.get_screen("arrived").set_destination(dest)
        self.manager.current = "arrived"

    def cancel(self, instance):
        if self._arrival_event:
            self._arrival_event.cancel()
            self._arrival_event = None
        speak("Cancelled. Where would you like to go?")
        self.manager.current = "home"


class ArrivedScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation="vertical", padding=40, spacing=20)
        self.title_label = Label(text="You've arrived!", font_size="30sp")
        done_btn = Button(text="Done", size_hint=(1, 0.2), font_size="18sp")
        done_btn.bind(on_press=self.done)

        layout.add_widget(self.title_label)
        layout.add_widget(done_btn)
        self.add_widget(layout)

    def set_destination(self, dest):
        self.title_label.text = f"You've arrived at {dest['label']}!"

    def done(self, instance):
        self.manager.current = "home"


class WayfinderApp(App):
    def build(self):
        Window.size = (1024, 600)   # roughly touchscreen-kiosk shaped
        # Window.fullscreen = True  # uncomment on the actual touchscreen/robot
        sm = ScreenManager()
        sm.add_widget(HomeScreen(name="home"))
        sm.add_widget(NavScreen(name="nav"))
        sm.add_widget(ArrivedScreen(name="arrived"))
        return sm


if __name__ == "__main__":
    WayfinderApp().run()