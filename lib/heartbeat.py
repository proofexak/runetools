"""
Session heartbeat (PRO-99) — a daemon thread that lets the web app tell a live
bot from a dead one, and see a pause the moment it starts.

While a session is open it emits to the session's event log:
  heartbeat    on start, then every `interval` s: state, run, paused
  pause_start  when the bot gets paused (O, the overlay, botctl), state
  pause_end    when it resumes, state — the runner's `pause` event (with
               seconds) is still logged by its pause gate as before; a pause
               taken inside an action's own pause.wait() only gets this one

It polls the pause flag instead of hooking pause.toggle(), so nothing is ever
emitted from a signal handler or the keyboard listener. It never raises into
the bot, and stop() (called before session_end) ends it.
"""
import threading, time

INTERVAL = 30.0   # seconds between heartbeats
POLL     = 0.2    # how often the pause flag is checked


class Heartbeat:
    def __init__(self, log, stats, is_paused, interval=None, poll=None, clock=time.monotonic):
        self.log, self.stats, self.is_paused = log, stats, is_paused
        self.interval = INTERVAL if interval is None else interval
        self.poll = POLL if poll is None else poll
        self.clock = clock
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="heartbeat", daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self, timeout=2.0):
        self._stop.set()
        if self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout)

    def _run(self):
        paused, due = False, self.clock()   # first beat at once: marks the session as heartbeating
        while not self._stop.wait(self.poll):
            try:
                now_paused = bool(self.is_paused())
                state = self.stats.get("step")
                if now_paused != paused:
                    paused = now_paused
                    self.log.emit("pause_start" if paused else "pause_end", state=state)
                if self.clock() >= due:
                    due = self.clock() + self.interval
                    self.log.emit("heartbeat", state=state, run=self.stats.get("run"), paused=paused)
            except Exception:
                pass   # never take the bot down; try again next poll
