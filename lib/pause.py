"""
Global pause/stop state — import this from any bot module.
Call setup() once at startup to register the hotkey.
"""
import time
from pynput import keyboard

_paused         = False
_force_stop     = False
_listener       = None
_pause_hotkey   = "o"
_stop_hotkey    = "p"   # None: no character stop key
_stop_key       = None  # pynput special-key name, e.g. "end"
_suppress_until = 0.0   # time.time() before which hotkeys are ignored


class ForceStop(Exception):
    pass


def setup(pause_hotkey="o", stop_hotkey="p", stop_key=None):
    """
    pause_hotkey: character that toggles pause/resume.
    stop_hotkey:  character that force-stops (None to disable).
    stop_key:     optional pynput special-key name (e.g. "end", "f12") that
                  also force-stops, even while paused.
    """
    global _listener, _pause_hotkey, _stop_hotkey, _stop_key
    _pause_hotkey = pause_hotkey.lower()
    _stop_hotkey  = stop_hotkey.lower() if stop_hotkey else None
    _stop_key     = stop_key

    stop_vk = getattr(keyboard.Key, stop_key, None) if stop_key else None

    def _on_press(key):
        if stop_vk is not None and key == stop_vk:
            print(f"\n[FORCE STOP] {stop_key} pressed.")
            force_stop()
            return
        char = getattr(key, "char", None)
        if char:
            _handle_char(char)

    _listener = keyboard.Listener(on_press=_on_press)
    _listener.start()


def _handle_char(char):
    if time.time() < _suppress_until:
        return
    char = char.lower()
    if char == _pause_hotkey:
        toggle()
    elif _stop_hotkey and char == _stop_hotkey:
        force_stop()
        print("\n[FORCE STOP] Stopping...")


def suppress_hotkeys(seconds):
    """Ignore hotkeys for `seconds` — the listener also sees the bot's own
    synthetic keystrokes, so typing e.g. "dragonhide" would press O."""
    global _suppress_until
    _suppress_until = max(_suppress_until, time.time() + seconds)


def set_paused(value):
    """Pause (True) or resume (False); a no-op if already in that state."""
    if bool(value) != _paused:
        toggle()


def hint():
    """Operator-facing key help for the configured hotkeys."""
    stops = [k.upper() for k in (_stop_hotkey,) if k] + ([_stop_key.title()] if _stop_key else [])
    stop = f", {' or '.join(stops)} to force-stop" if stops else ""
    return f"Press {_pause_hotkey.upper()} to pause{stop}."


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
    """Block while paused; raise ForceStop on P. Returns True if it blocked, so
    callers timing something (e.g. an idle timeout) can discount the pause."""
    blocked = False
    while _paused:
        if _force_stop:
            raise ForceStop()
        blocked = True
        time.sleep(0.2)
    if _force_stop:
        raise ForceStop()
    return blocked


def is_paused():
    return _paused
