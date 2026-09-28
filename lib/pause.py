"""
Global pause/stop state — import this from any bot module.
Call setup() once at startup to register the hotkey.
"""
import time
from pynput import keyboard

_paused     = False
_force_stop = False
_listener   = None


class ForceStop(Exception):
    pass


def setup(hotkey="p", stop_key=None):
    """
    hotkey: single character that toggles pause/resume.
    stop_key: optional pynput special-key name (e.g. "end", "f12") that
    force-stops the bot immediately, even while paused.
    """
    global _listener

    stop_vk = getattr(keyboard.Key, stop_key, None) if stop_key else None

    def _on_press(key):
        if getattr(key, "char", None) and key.char.lower() == hotkey.lower():
            toggle()
        elif stop_vk is not None and key == stop_vk:
            print(f"\n[FORCE STOP] {stop_key} pressed.")
            force_stop()

    _listener = keyboard.Listener(on_press=_on_press)
    _listener.start()


def toggle():
    global _paused
    _paused = not _paused
    print(f"\n{'[PAUSED] Press P to resume.' if _paused else '[RESUMED]'}")


def force_stop():
    global _force_stop
    _force_stop = True


def reset():
    global _paused, _force_stop
    _paused     = False
    _force_stop = False


def wait():
    while _paused:
        if _force_stop:
            raise ForceStop()
        time.sleep(0.2)
    if _force_stop:
        raise ForceStop()


def is_paused():
    return _paused
