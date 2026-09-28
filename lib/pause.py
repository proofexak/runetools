"""
Global pause/stop state — import this from any bot module.
Call setup() once at startup to register the hotkey.
"""
import time
from pynput import keyboard

_paused     = False
_force_stop = False
_listener   = None
_pause_hotkey = "o"


class ForceStop(Exception):
    pass


def setup(pause_hotkey="o", stop_hotkey="p", stop_key=None):
    """
    pause_hotkey: character that toggles pause/resume.
    stop_hotkey:  character that force-stops (None to disable).
    stop_key:     optional pynput special-key name (e.g. "end", "f12") that
                  also force-stops, even while paused.
    """
    global _listener, _pause_hotkey
    _pause_hotkey = pause_hotkey

    stop_vk = getattr(keyboard.Key, stop_key, None) if stop_key else None

    def _on_press(key):
        if stop_vk is not None and key == stop_vk:
            print(f"\n[FORCE STOP] {stop_key} pressed.")
            force_stop()
            return
        char = getattr(key, "char", None)
        if not char:
            return
        char = char.lower()
        if char == pause_hotkey.lower():
            toggle()
        elif stop_hotkey and char == stop_hotkey.lower():
            force_stop()
            print("\n[FORCE STOP] Stopping...")

    _listener = keyboard.Listener(on_press=_on_press)
    _listener.start()


def toggle():
    global _paused
    _paused = not _paused
    print(f"\n{f'[PAUSED] Press {_pause_hotkey.upper()} to resume.' if _paused else '[RESUMED]'}")


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
