"""
Structured session events — one JSON object per line (JSON Lines).

Each bot session writes <bot>/log/<name>_YYYYMMDD_HHMMSS.jsonl next to its text
log (lib/session.py opens it; lib/state_machine.py emits steps). Errors that
happen outside a session — a bot failing before its session starts, an
uncaught exception anywhere — go to <repo>/log/launcher.jsonl.
Read them with `python -m lib.logreport`.

Logging must never stop a bot: unserialisable values are written as repr(),
and a failed write prints one warning and is otherwise ignored.
"""
import json, os, sys, threading, traceback
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_current = None
_warned  = False


def _warn(err):
    global _warned
    if not _warned:
        _warned = True
        try:
            print(f"[events] Structured log unavailable: {err!r}", file=sys.stderr)
        except Exception:
            pass   # nowhere left to complain to; never raise into a bot


class EventLog:
    def __init__(self, path, bot, session):
        self.path, self.bot, self.session = path, bot, session
        self.paused_seconds = 0.0   # accumulated by the runner's pause gate
        try:
            self._f = open(path, "a", encoding="utf-8")
        except OSError as e:
            self._f = None
            _warn(e)

    def emit(self, event, **fields):
        record = {"ts": datetime.now().isoformat(timespec="milliseconds"),
                  "session": self.session, "bot": self.bot, "event": event, **fields}
        if self._f is None:
            return
        try:
            self._f.write(json.dumps(record, default=repr) + "\n")
            self._f.flush()
        except Exception as e:
            _warn(e)

    def close(self):
        if self._f is not None:
            try:
                self._f.close()
            except Exception:
                pass
            self._f = None


def start(path, bot, session):
    """Open the session's event log and make it current()."""
    global _current
    _current = EventLog(path, bot, session)
    return _current


def current():
    """The running session's EventLog, or None outside a session."""
    return _current


def finish():
    global _current
    if _current is not None:
        _current.close()
    _current = None


def error_fields(exc):
    """type / message / traceback of an exception — robust to one whose str() raises."""
    name = type(exc).__name__
    try:
        message = str(exc)
    except Exception:
        message = f"<unprintable {name}>"
    try:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    except Exception:
        tb = f"{name}: {message}"
    return {"type": name, "message": message, "traceback": tb}


def record_error(exc, where):
    """Log an error to the running session if there is one, else to launcher.jsonl."""
    log = current()
    if log is not None:
        log.emit("error", where=where, **error_fields(exc))
        mark_logged(exc)
    else:
        launcher_error(None, exc, where)


def mark_logged(exc):
    """Flag an exception a session already recorded, so the launcher-level
    hooks don't record it again."""
    try:
        exc._runetools_logged = True
    except Exception:
        pass


def was_logged(exc):
    return getattr(exc, "_runetools_logged", False)


def launcher_error(bot, exc, where, root=None):
    """Append an error that happened outside any session to <root>/log/launcher.jsonl
    (root defaults to the repo root)."""
    root = root or ROOT
    try:
        os.makedirs(os.path.join(root, "log"), exist_ok=True)
    except OSError as e:
        _warn(e)
    log = EventLog(os.path.join(root, "log", "launcher.jsonl"), bot, None)
    log.emit("error", where=where, **error_fields(exc))
    log.close()
    mark_logged(exc)


def install_excepthooks(root=None):
    """Record every uncaught exception (main thread and other threads, e.g. the
    overlay) in launcher.jsonl, then let the previous hook run as usual."""
    prev_sys, prev_thread = sys.excepthook, threading.excepthook

    def sys_hook(exc_type, exc, tb):
        if exc is not None and not was_logged(exc):
            launcher_error(None, exc, "uncaught", root=root)
        prev_sys(exc_type, exc, tb)

    def thread_hook(args):
        exc = args.exc_value
        if exc is not None and not was_logged(exc):
            launcher_error(None, exc, f"thread {args.thread.name if args.thread else '?'}", root=root)
        prev_thread(args)

    sys.excepthook, threading.excepthook = sys_hook, thread_hook
