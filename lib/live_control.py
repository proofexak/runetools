"""
"Take control" from the web app's live view (PRO-89): a human drives the game over VNC
while the bot waits.

pyautogui and the VNC viewer share one X display, so the bot must be paused before the
human's mouse goes live. The web app and the bots only share files in data/ (like
data/active_account), so the hand-over is two small JSON files:

  data/live_control.json      written by the web app: {"id": "<request id>", "held": true|false}
  data/live_control_ack.json  written here:           {"id", "held", "safe", "pid"}

A watcher thread polls the request and applies it — held: pause.hold() (bot paused, O/P
ignored so the human can type); released: pause.unhold() (pause state from before, hotkeys
back). It answers whenever (id, held, safe) changes; `safe` = no bot step is running
(pause.idle()). The web app enables the mouse/keyboard once it sees safe for its id, and
treats no answer at all as "no bot running here".

A missing or unreadable request means released. Never raises into a bot.
"""
import json, os, threading

import lib.pause as pause

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLL = 0.25   # seconds between checks of the request file


def request_path(root=None):
    return os.path.join(root or ROOT, "data", "live_control.json")


def ack_path(root=None):
    return os.path.join(root or ROOT, "data", "live_control_ack.json")


def read_request(path):
    """(id, held) from the web app's request file; (None, False) if missing or unreadable."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return (str(data["id"]), data.get("held") is True)
    except Exception:
        return None, False


def write_json(path, data):
    """Write atomically (the web app may read at any moment). False if it couldn't."""
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
        return True
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


class Watcher:
    def __init__(self, root=None, pause_mod=pause):
        self.request, self.ack = request_path(root), ack_path(root)
        self.pause = pause_mod
        self.answered = None          # last (id, held, safe) written to the ack file
        self._stop = threading.Event()

    def poll_once(self):
        rid, held = read_request(self.request)
        if held:
            self.pause.hold()
        else:
            self.pause.unhold()
        if rid is None:               # nobody asked: nothing to answer
            return
        state = (rid, held, bool(self.pause.idle()))
        if state != self.answered and write_json(self.ack, {
                "id": rid, "held": held, "safe": state[2], "pid": os.getpid()}):
            self.answered = state

    def run(self):
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:
                pass                  # never take the bot down; try again next poll
            self._stop.wait(POLL)

    def start(self):
        threading.Thread(target=self.run, name="live-control", daemon=True).start()
        return self

    def stop(self):
        self._stop.set()


def start(root=None):
    """Start watching for the web app's take/release requests (daemon thread)."""
    return Watcher(root).start()
