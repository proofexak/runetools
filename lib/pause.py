"""
Global pause/stop state — import this from any bot module.
Call setup() once at startup to register the hotkey.
"""
import time
import keyboard

_paused     = False
_force_stop = False


class ForceStop(Exception):
    pass


def setup(hotkey="p"):
    keyboard.add_hotkey(hotkey, toggle)


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
