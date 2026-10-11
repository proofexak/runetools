"""
Failure screenshots (PRO-91) — what the screen looked like when a step failed.

When a handler returns a failing result (logreport.FAILURE_RESULTS: "fail" /
"not_found") run_machine asks for one, and run_session asks for one when it
records an `error`. The whole of monitor 1 is grabbed, the regions / points the
failing state uses are drawn on it (vision.draw_marks) and it is saved next to
the session log as <log name>_<stamp>_<n>_<state>.png; the `step` / `error`
event gets `screenshot: "<file name>"`.

Which config regions belong to which state is the bot's declaration: STATE_MARKS
in its states.py ({state: [config names]}), turned into `marks` for run_session
by config_marks(). A name "ge.X" / "energy.X" is lib/ge_config.py's /
lib/energy_config.py's X.

Like the event log this never raises into a bot: a grab or save that fails
prints one warning and the event goes without `screenshot`. At most
MAX_PER_SESSION per session (a bot failing in a loop must not fill the disk).
"""
import importlib, os, re, sys, time

from lib.logreport import FAILURE_RESULTS

MAX_PER_SESSION = 20
ERROR_ATTR = "_runetools_screenshot"   # the file name, on an exception a session recorded

# prefix of a config name → loader of the lib config it names
LIB_CONFIGS = {
    "ge":     lambda: importlib.import_module("lib.ge_config"),
    "energy": lambda: importlib.import_module("lib.energy_config"),
}

_current = None
_warned = False


def _warn(msg):
    global _warned
    if not _warned:
        _warned = True
        try:
            print(f"[screenshots] {msg}", file=sys.stderr)
        except Exception:
            pass


def grab_screen():
    """BGR frame of the whole of monitor 1 — in the coordinates the configs use."""
    import lib.screen as screen
    frame, _ = screen.grab(screen.screen_rect())
    return frame


def file_name(log_path, n, state):
    """<log name without .jsonl>_<n>_<state>.png, with the state reduced to [A-Za-z0-9_-]."""
    base = os.path.splitext(os.path.basename(log_path))[0]
    return f"{base}_{n}_{re.sub(r'[^A-Za-z0-9_-]', '_', str(state))}.png"


def config_marks(table, config):
    """marks(state) -> [(name, value)] for the names `table` lists for that state, read from
    `config` (or a lib config for "ge." / "energy." names) when the screenshot is taken.
    A name the config doesn't have (an older calibrated file) is skipped."""
    def marks(state):
        out = []
        for name in table.get(state, ()):
            prefix, dot, attr = name.partition(".")
            try:
                source = LIB_CONFIGS[prefix]() if dot and prefix in LIB_CONFIGS else config
                value = getattr(source, attr if dot and prefix in LIB_CONFIGS else name)
            except Exception:
                continue
            out.append((name, value))
        return out
    return marks


class Shooter:
    """One session's screenshots: numbered files next to its log, up to `cap`."""

    def __init__(self, log_path, marks=None, cap=None):
        self.log_path = log_path
        self.folder = os.path.dirname(os.path.abspath(log_path))
        self.marks = marks
        self.cap = MAX_PER_SESSION if cap is None else cap
        self.taken = 0
        self._capped = False

    def take(self, state, title=None):
        """Grab, draw `state`'s marks and `title`, save; the file name, or None (cap reached,
        or anything failed)."""
        try:
            if self.taken >= self.cap:
                if not self._capped:
                    self._capped = True
                    print(f"  [screenshots] {self.cap} taken this session — no more")
                return None
            import lib.vision as vision
            from PIL import Image
            frame = grab_screen()
            try:
                marks = list(self.marks(state)) if self.marks else []
            except Exception:
                marks = []
            image = vision.draw_marks(frame, marks, title=title)
            name = file_name(self.log_path, self.taken + 1, state)
            Image.fromarray(image[:, :, ::-1]).save(os.path.join(self.folder, name))
            self.taken += 1
            return name
        except Exception as e:
            _warn(f"screenshot not saved: {e!r}")
            return None


def start(log_path, marks=None):
    """The running session's shooter (run_session), saving next to `log_path`."""
    global _current
    _current = Shooter(log_path, marks)
    return _current


def current():
    return _current


def finish():
    global _current
    _current = None


def take(state, title=None):
    shooter = _current
    return shooter.take(state, title) if shooter is not None else None


def step_fields(state, result):
    """{"screenshot": name} for a failing step result (taken now), else {}."""
    try:
        if _current is None or not isinstance(result, str) or result not in FAILURE_RESULTS:
            return {}
        name = take(state, f"{time.strftime('%H:%M:%S')}  {state} -> {result}")
        return {"screenshot": name} if name else {}
    except Exception:
        return {}


def tag_error(exc, state):
    """Screenshot for an error the session is about to record: the file name goes on the
    exception, where events.error_fields picks it up. Not for a force stop (P) or Ctrl+C."""
    try:
        if _current is None or not isinstance(exc, Exception) or getattr(exc, ERROR_ATTR, None):
            return
        import lib.pause as pause
        if isinstance(exc, pause.ForceStop):
            return
        name = take(state, f"{time.strftime('%H:%M:%S')}  {state}: {type(exc).__name__}")
        if name:
            setattr(exc, ERROR_ATTR, name)
    except Exception:
        pass
