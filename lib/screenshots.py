"""
Failure screenshots (PRO-91) — what the screen looked like when a step failed.

When a handler returns a failing result (logreport.FAILURE_RESULTS: "fail" /
"not_found") run_machine asks for one, and run_session asks for one when it
records an `error`. The whole of monitor 1 is grabbed, the regions / points the
failing state uses are drawn on it (vision.draw_marks) and it is saved next to
the session log as <log name>_<stamp>_<n>_<state>.png; the `step` / `error`
event gets `screenshot: "<file name>"`.

A handler that waits before it reports a failure (a miner's retry wait after
"no rock") calls failed_now(result) at the miss: the shot is taken then, and the
step event uses it instead of a late one that might show the target back.

Which config regions belong to which state is the bot's declaration: STATE_MARKS
in its states.py ({state: [config names]}), turned into `marks` for run_session
by config_marks(). A name "ge.X" / "energy.X" is lib/ge_config.py's /
lib/energy_config.py's X.

Like the event log this never raises into a bot: a grab or save that fails
prints one warning and the event goes without `screenshot`. Failing steps get
at most MAX_PER_STATE per state (a routine "not_found" loop — a vein, a rock —
leaves room for the rarer failures) and MAX_PER_SESSION in all (a bot failing
in a loop must not fill the disk); the session's error always gets one.
"""
import importlib, os, re, sys, time

from lib.logreport import FAILURE_RESULTS

MAX_PER_SESSION = 20
MAX_PER_STATE   = 5
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
    """One session's screenshots: numbered files next to its log."""

    def __init__(self, log_path, marks=None):
        self.log_path = log_path
        self.folder = os.path.dirname(os.path.abspath(log_path))
        self.marks = marks
        self.taken = 0
        self.per_state = {}
        self._capped = set()
        self.state = None      # the state whose handler is running (run_machine → enter)
        self.pending = None    # its shot taken early by failed_now

    def _over_cap(self, state):
        for key, n, cap in (("session", self.taken, MAX_PER_SESSION),
                            (state, self.per_state.get(state, 0), MAX_PER_STATE)):
            if n >= cap:
                if key not in self._capped:
                    self._capped.add(key)
                    print(f"  [screenshots] {cap} taken {'this session' if key == 'session' else 'in ' + str(state)}"
                          " — no more")
                return True
        return False

    def take(self, state, title=None, capped=True):
        """Grab, draw `state`'s marks and `title`, save; the file name, or None (over a cap,
        unless `capped` is False, or anything failed)."""
        try:
            if capped and self._over_cap(state):
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
            self.per_state[state] = self.per_state.get(state, 0) + 1
            return name
        except Exception as e:
            _warn(f"screenshot not saved: {e!r}")
            return None


def start(log_path, marks=None):
    """The running session's shooter (run_session), saving next to `log_path`."""
    global _current, _warned
    _current = Shooter(log_path, marks)
    _warned = False        # each session warns once of its own failures
    return _current


def current():
    return _current


def finish():
    global _current
    _current = None


def take(state, title=None, capped=True):
    shooter = _current
    return shooter.take(state, title, capped) if shooter is not None else None


def _failing(result):
    return isinstance(result, str) and result in FAILURE_RESULTS


def _step_title(state, result):
    return f"{time.strftime('%H:%M:%S')}  {state} -> {result}"


def enter(state):
    """run_machine: `state`'s handler is about to run."""
    shooter = _current
    if shooter is not None:
        shooter.state, shooter.pending = state, None


def failed_now(result):
    """For a handler that waits (a retry delay) before returning a failing `result`: take
    the step's screenshot now, at the miss. The step event then names this one."""
    try:
        shooter = _current
        if shooter is None or shooter.state is None or shooter.pending or not _failing(result):
            return
        shooter.pending = shooter.take(shooter.state, _step_title(shooter.state, result))
    except Exception:
        pass


def step_fields(state, result):
    """{"screenshot": name} for a failing step result — the one failed_now took, else
    taken now — or {}."""
    try:
        shooter = _current
        if shooter is None:
            return {}
        pending, shooter.pending = shooter.pending, None
        if not _failing(result):
            return {}
        name = pending or take(state, _step_title(state, result))
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
        state = _current.state or state   # the machine's state: a bot may relabel stats["step"]
        name = take(state, f"{time.strftime('%H:%M:%S')}  {state}: {type(exc).__name__}", capped=False)
        if name:
            setattr(exc, ERROR_ATTR, name)
    except Exception:
        pass
