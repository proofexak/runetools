"""
Manual mode's main process in the bot container (PRO-90): `python3 -m lib.manual`,
run by docker-compose when BOT is unset (unattended mode runs lib.headless instead).

It starts RuneLite and the bot menu (run.py) when the web app asks — then everything
else is done by hand in the live view. Like "Take control" (lib/live_control.py), the web
app and the container only share files in data/:

  data/manual_request.json  written by the web app: {"id": "<request id>", "action": "start"}
  data/manual_status.json   written here every STATUS_EVERY s:
                            {"pid", "ts" (epoch s), "runelite", "menu", "phase",
                             "handled" (last request id done), "error"}

A fresh status file is also the web app's "manual mode is up" signal. "start" launches
only what's missing — RuneLite first (waits for its window), then run.py — so pressing
Start twice never gives two of either. Detection scans /proc, so a RuneLite or menu
started some other way (`docker compose exec`) counts too.

As PID 1 it also reaps orphaned processes, and on SIGTERM (docker stop) it sends SIGINT
to the bot menu — a running session then ends "interrupted" with its teardown and
session_end — and waits for it before exiting.
"""
import json, os, signal, subprocess, sys, threading, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS_EVERY   = 2.0     # seconds between status writes / request checks
WINDOW_TIMEOUT = 120.0   # RuneLite's window must appear within this (first start downloads)
WINDOW_SETTLE  = 3.0     # then a moment before the menu draws over it
STOP_GRACE     = 20.0    # docker stop: how long the menu gets to end its session


def request_path(root=None):
    return os.path.join(root or ROOT, "data", "manual_request.json")


def status_path(root=None):
    return os.path.join(root or ROOT, "data", "manual_status.json")


# ── pure parts ────────────────────────────────────────────────────────────────

def is_runelite(argv):
    """RuneLite's JVM: java with the RuneLite client on its command line."""
    return bool(argv) and os.path.basename(argv[0]).startswith("java") and \
        any("runelite" in a.lower() for a in argv[1:])


def is_menu(argv):
    """The bot menu: a python running run.py (not a test run, not this module)."""
    return bool(argv) and "python" in os.path.basename(argv[0]) and \
        any(os.path.basename(a) == "run.py" for a in argv[1:])


def running(cmdlines):
    """(runelite, menu) from the argv lists of the running processes."""
    return any(is_runelite(a) for a in cmdlines), any(is_menu(a) for a in cmdlines)


def plan(runelite, menu):
    """What a start request launches, in order."""
    return (["runelite"] if not runelite else []) + (["menu"] if not menu else [])


def read_request(path):
    """(id, action) from the web app's request file; (None, None) if missing / unreadable."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return str(data["id"]), str(data.get("action", ""))
    except Exception:
        return None, None


# ── the process ───────────────────────────────────────────────────────────────

def proc_cmdlines(proc="/proc"):
    out = []
    for pid in os.listdir(proc):
        if not pid.isdigit():
            continue
        try:
            with open(os.path.join(proc, pid, "cmdline"), "rb") as f:
                argv = [a.decode("utf-8", "replace") for a in f.read().split(b"\0") if a]
        except OSError:
            continue
        if argv:
            out.append(argv)
    return out


def pids_matching(test, proc="/proc"):
    pids = []
    for pid in os.listdir(proc):
        if not pid.isdigit() or int(pid) == os.getpid():
            continue
        try:
            with open(os.path.join(proc, pid, "cmdline"), "rb") as f:
                argv = [a.decode("utf-8", "replace") for a in f.read().split(b"\0") if a]
        except OSError:
            continue
        if argv and test(argv):
            pids.append(int(pid))
    return pids


def write_json(path, data):
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except Exception as e:
        print(f"[manual] can't write {path}: {e!r}", file=sys.stderr)


def client_window_in(tree):
    """The RuneLite client's window in `xwininfo -root -tree` output: titled "RuneLite" or
    "RuneLite - <name>" — not the "RuneLite Launcher" that comes first and downloads it."""
    return '"RuneLite"' in tree or '"RuneLite - ' in tree


def runelite_window_up():
    """True once the RuneLite client's X window exists (xwininfo from x11-utils)."""
    try:
        out = subprocess.run(["xwininfo", "-root", "-tree"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return False
    return client_window_in(out)


class Manual:
    def __init__(self, root=None, launch=None, scan=None, window_up=runelite_window_up, clock=time.monotonic,
                 sleep=time.sleep):
        self.root = root or ROOT
        self.launch = launch or self._launch
        self.scan = scan or proc_cmdlines
        self.window_up, self.clock, self.sleep = window_up, clock, sleep
        self.phase, self.error, self.handled = "idle", None, None
        self._busy = threading.Lock()

    # what runs a launch for real: detached, logs in /tmp
    def _launch(self, what):
        argv = ["runelite"] if what == "runelite" else [sys.executable, "run.py"]
        log = open(f"/tmp/manual-{what}.log", "ab")
        subprocess.Popen(argv, cwd=self.root, stdout=log, stderr=log, start_new_session=True)

    def status(self):
        runelite, menu = running(self.scan())
        return {"pid": os.getpid(), "ts": time.time(), "runelite": runelite, "menu": menu,
                "phase": self.phase, "handled": self.handled, "error": self.error}

    def start(self, request_id):
        """Launch what's missing; runs on its own thread so status keeps flowing."""
        with self._busy:
            self.error = None
            try:
                for what in plan(*running(self.scan())):
                    self.phase = f"starting_{what}"
                    self.launch(what)
                    if what == "runelite":
                        self._wait_for_window()
            except Exception as e:
                self.error = f"{type(e).__name__}: {e}"
            finally:
                self.phase, self.handled = "idle", request_id

    def _wait_for_window(self):
        deadline = self.clock() + WINDOW_TIMEOUT
        while self.clock() < deadline:
            if self.window_up():
                self.sleep(WINDOW_SETTLE)
                return
            self.sleep(1.0)
        raise TimeoutError("RuneLite's window didn't appear")

    def poll_once(self, seen):
        """One tick: act on a new request, write the status. Returns the request id seen."""
        rid, action = read_request(request_path(self.root))
        if rid and rid != seen and action == "start" and not self._busy.locked():
            threading.Thread(target=self.start, args=(rid,), name="manual-start", daemon=True).start()
            seen = rid
        elif rid and rid != seen and action != "start":
            self.handled, seen = rid, rid          # unknown action: acknowledge, ignore
        write_json(status_path(self.root), self.status())
        return seen


def _reap_forever():
    """PID 1 inherits every orphan (RuneLite's launcher re-execs, exec'd shells)."""
    while True:
        try:
            os.waitpid(-1, 0)
        except ChildProcessError:
            time.sleep(1.0)
        except Exception:
            time.sleep(1.0)


def _stop(signum, frame):
    menus = pids_matching(is_menu)
    for pid in menus:
        try:
            os.kill(pid, signal.SIGINT)        # ends a session as "interrupted", with teardown
        except OSError:
            pass
    deadline = time.monotonic() + STOP_GRACE
    while menus and time.monotonic() < deadline:
        menus = [p for p in menus if os.path.exists(f"/proc/{p}")]
        time.sleep(0.5)
    sys.exit(0)


def main():
    m = Manual()
    # an old request from before this start must not fire again
    seen, _ = read_request(request_path(m.root))
    m.handled = seen
    threading.Thread(target=_reap_forever, name="reaper", daemon=True).start()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    print("[manual] manual mode: waiting for the web app (or start RuneLite / run.py by hand)")
    while True:
        seen = m.poll_once(seen)
        time.sleep(STATUS_EVERY)


if __name__ == "__main__":
    main()
