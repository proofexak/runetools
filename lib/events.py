"""
Structured session events — one JSON object per line (JSON Lines).

Each bot session writes <bot>/log/<name>_YYYYMMDD_HHMMSS.jsonl next to its text
log (lib/session.py opens it; lib/state_machine.py emits steps). Errors that
happen outside a session — a bot failing before its session starts, an
uncaught exception anywhere — go to <repo>/log/launcher.jsonl.
Read them with `python -m lib.logreport`.

Logging must never stop a bot: unserialisable values are written as repr(),
and a failed write prints one warning and is otherwise ignored.

Live push (PRO-99): after a line is written, it is also sent to the web app
(POST <RUNETOOLS_APP_URL>/api/ingest, bearer token from data/bot_token) with its
file key and byte offset, so the dashboard sees it at once. The file stays the
source of truth: the app tails it too and ignores a pushed line it already has.
Sending happens on a background thread from a bounded queue (full = dropped),
one try per line with a short timeout — it never blocks or raises into a bot.
No token or an empty RUNETOOLS_APP_URL means nothing is pushed.
"""
import json, os, queue, sys, threading, time, traceback, urllib.request
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

APP_URL_VAR     = "RUNETOOLS_APP_URL"
DEFAULT_APP_URL = "http://127.0.0.1:8778"
PUSH_TIMEOUT    = 1.0
PUSH_QUEUE_SIZE = 500
PUSH_BACKOFF    = 5.0   # seconds of not trying after a failed send

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


def bot_token_path(root=None):
    return os.path.join(root or ROOT, "data", "bot_token")


def push_target():
    """(app url, token) to push to, or None when pushing is off (empty
    RUNETOOLS_APP_URL, no data/bot_token)."""
    try:
        url = os.environ.get(APP_URL_VAR, DEFAULT_APP_URL).strip().rstrip("/")
        if not url:
            return None
        with open(bot_token_path(), encoding="utf-8") as f:
            token = f.readline().strip()
        return (url, token) if token else None
    except Exception:
        return None


def file_key(path):
    """The log's path relative to the repo, "/"-separated — how the app keys
    files. None for a file outside the repo (the app couldn't match it)."""
    try:
        rel = os.path.relpath(os.path.abspath(path), ROOT)
    except ValueError:            # another drive on Windows
        return None
    if rel == os.pardir or rel.startswith(os.pardir + os.sep) or os.path.isabs(rel):
        return None
    return rel.replace(os.sep, "/")


class Pusher:
    """Sends log lines to the app from one daemon thread. send() never blocks:
    a full queue drops the line (the app's tailer still reads it from the file).
    After a failed send, lines are dropped untried for `backoff` seconds — a
    connect to a closed port takes ~1 s on Windows, and the app's tailer picks
    up everything it missed from the file anyway."""

    def __init__(self, url, maxsize=PUSH_QUEUE_SIZE, timeout=PUSH_TIMEOUT, backoff=PUSH_BACKOFF,
                 opener=None, clock=time.monotonic):
        self.url = url
        self.timeout, self.backoff, self.clock = timeout, backoff, clock
        self.dropped = 0
        self._down_until = 0.0
        self._q = queue.Queue(maxsize=maxsize)
        # never through a system / registry proxy: the app is local (or a compose service)
        self._open = opener or urllib.request.build_opener(urllib.request.ProxyHandler({})).open
        threading.Thread(target=self._run, name="events-push", daemon=True).start()

    def send(self, token, key, offset, line):
        try:
            self._q.put_nowait((token, key, offset, line))
        except queue.Full:
            self.dropped += 1
        except Exception:
            pass

    def join(self):
        """Wait until every queued line was tried (tests)."""
        self._q.join()

    def _run(self):
        while True:
            item = self._q.get()
            try:
                if self.clock() < self._down_until:
                    self.dropped += 1
                else:
                    self._post(*item)
            except Exception:    # app down / slow / refusing: the file is the fallback
                try:
                    self._down_until = self.clock() + self.backoff
                except Exception:
                    pass
            finally:
                self._q.task_done()

    def _post(self, token, key, offset, line):
        body = json.dumps({"file": key, "offset": offset, "line": line}).encode("utf-8")
        req = urllib.request.Request(self.url + "/api/ingest", data=body, method="POST", headers={
            "content-type": "application/json", "authorization": f"Bearer {token}"})
        with self._open(req, timeout=self.timeout) as res:
            res.read()


_pushers = {}
_pushers_lock = threading.Lock()


def pusher_for(url):
    """One Pusher (thread + queue) per app URL, for the life of the process."""
    with _pushers_lock:
        if url not in _pushers:
            _pushers[url] = Pusher(url)
        return _pushers[url]


class EventLog:
    def __init__(self, path, bot, session, push=None):
        """push: (url, token) to send lines to the web app; None = push_target();
        False = never push."""
        self.path, self.bot, self.session = path, bot, session
        self.paused_seconds = 0.0   # accumulated by the runner's pause gate
        self._lock = threading.Lock()   # the heartbeat thread emits too
        self._push = None
        try:
            # binary: "\n" on every platform, so tell() is the line's exact byte offset
            self._f = open(path, "ab")
        except OSError as e:
            self._f = None
            _warn(e)
            return
        try:
            target = push_target() if push is None else push
            key = file_key(path) if target else None
            if key:
                self._push = (pusher_for(target[0]), target[1], key)
        except Exception:
            self._push = None

    def emit(self, event, **fields):
        record = {"ts": datetime.now().isoformat(timespec="milliseconds"),
                  "session": self.session, "bot": self.bot, "event": event, **fields}
        if self._f is None:
            return
        try:
            line = json.dumps(record, default=repr)
            with self._lock:
                offset = self._f.tell()
                self._f.write(line.encode("utf-8") + b"\n")
                self._f.flush()
                if self._push:       # under the lock, so lines are queued in file order
                    pusher, token, key = self._push
                    pusher.send(token, key, offset, line)
        except Exception as e:
            _warn(e)

    def close(self):
        if self._f is not None:
            try:
                with self._lock:
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


def launcher_event(bot, event, root=None, **fields):
    """Append a non-session event (e.g. the unattended supervisor's) to
    <root>/log/launcher.jsonl (root defaults to the repo root)."""
    root = root or ROOT
    try:
        os.makedirs(os.path.join(root, "log"), exist_ok=True)
    except OSError as e:
        _warn(e)
    log = EventLog(os.path.join(root, "log", "launcher.jsonl"), bot, None, push=False)
    log.emit(event, **fields)
    log.close()


def launcher_error(bot, exc, where, root=None):
    """Append an error that happened outside any session to <root>/log/launcher.jsonl
    (root defaults to the repo root)."""
    root = root or ROOT
    try:
        os.makedirs(os.path.join(root, "log"), exist_ok=True)
    except OSError as e:
        _warn(e)
    log = EventLog(os.path.join(root, "log", "launcher.jsonl"), bot, None, push=False)
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
