"""
Unattended mode: keep RuneLite logged in, run one bot, restart it per policy.

    BOT=Tanning LAUNCH="Green Dragonhide" python -m lib.headless
    BOT="Choco Grind" LAUNCH=Run VALUE=500 python -m lib.headless

The container's main command when BOT is set (docker/docker-compose.yml).
Control it from the host with docker/botctl (signals):

    SIGUSR1  pause / resume      SIGUSR2  soft stop → idle    SIGINT  kill → idle
    SIGHUP   start (leave idle)  SIGTERM  force stop and exit

Idle never exits — the container and its VNC stay up for a human to look.
Supervisor events go to log/launcher.jsonl (`python -m lib.logreport supervisor`).
"""
import os, signal, sys, threading, time

import lib.events as events
import lib.pause as pause
from lib import supervisor as policy
from lib.supervisor import Outcome, Backoff, Budget, decide


def resolve(bot_name, launch_label, value, bots):
    """(Bot, start(stats)) for the names in BOT / LAUNCH; ValueError lists the choices."""
    bot = next((b for b in bots if b.name.lower() == (bot_name or "").lower()), None)
    if bot is None:
        raise ValueError(f"unknown BOT {bot_name!r}; choose one of: {', '.join(b.name for b in bots)}")
    launch = next((l for l in bot.launches if l.label.lower() == (launch_label or "").lower()), None)
    if launch is None:
        raise ValueError(f"unknown LAUNCH {launch_label!r} for {bot.name}; choose one of: "
                         f"{', '.join(l.label for l in bot.launches)}")
    if launch.ask_int:
        try:
            n = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{bot.name} / {launch.label} needs VALUE ({launch.ask_int})")
        return bot, (lambda stats: launch.start(stats, n))
    return bot, launch.start


class RealClient:
    """lib.client wired to the real screen, mouse and RuneLite process."""

    def credentials_saved(self):
        import lib.client as client
        return client.credentials_saved()

    def ensure_logged_in(self):
        import lib.client as client
        return client.ensure_logged_in()

    def logged_in(self):
        import lib.client as client
        frame, _ = client.grab_screen()
        return client.logged_in(client.load_templates(), frame)

    def kill(self):
        import lib.client as client
        client.kill()


class Supervisor:
    def __init__(self, bot, start, client, clock=time.time, sleeper=None, idle_waiter=None):
        self.bot, self.start, self.client, self.clock = bot, start, client, clock
        self.stats = {"run": 0, "step": "starting", "start": None, "stop": False}
        self._wake = threading.Event()
        self._sleep = sleeper or self._interruptible_sleep
        self._idle_wait = idle_waiter or self._wait_for_signal
        self.backoff, self.budget = Backoff(), Budget(clock)
        self.active, self.exiting, self.operator = True, False, False
        self.login_failures = 0

    # ── signals (handlers only set flags) ──────────────────────────────────────
    def on_pause(self):
        pause.toggle()

    def on_soft_stop(self):
        self.operator, self.active = True, False
        self.stats["stop"] = True
        self._wake.set()

    def on_kill(self):
        self.operator, self.active = True, False
        pause.force_stop()
        self._wake.set()

    def on_start(self):
        pause.reset()             # clear a previous kill's force-stop flag
        self.active = True
        self.backoff.reset()
        self.budget.reset()
        self.login_failures = 0
        self._wake.set()

    def on_term(self):
        self.exiting, self.active = True, False
        pause.force_stop()
        self._wake.set()

    # ── loop ───────────────────────────────────────────────────────────────────
    def _event(self, event, **fields):
        events.launcher_event(self.bot.name, event, **fields)

    def _interruptible_sleep(self, seconds):
        self._wake.wait(seconds)
        self._wake.clear()

    def _wait_for_signal(self):
        self._wake.wait()
        self._wake.clear()

    def _idle(self, why, reason=None):
        self.active = False
        self._event("idle", why=why, reason=reason)

    def _pause_before_retry(self, seconds, **fields):
        self._event("restart", delay=seconds, **fields)
        self._sleep(seconds)

    def _run_session(self):
        self.operator = False
        began = self.clock()
        try:
            self.start(self.stats)
            final, reason, crashed = self.stats.get("step"), self.stats.get("reason"), False
        except Exception as e:
            final, reason, crashed = "crashed", f"{type(e).__name__}: {e}", True
        return Outcome(final=final, reason=reason, crashed=crashed,
                       operator=self.operator, seconds=self.clock() - began)

    def run_forever(self):
        self._event("supervisor_start")
        while not self.exiting:
            if not self.active:
                self._idle_wait()
                continue
            if not self.client.credentials_saved():
                self._event("waiting", reason="no saved credentials (~/.runelite/credentials.properties)")
                self._sleep(policy.CREDENTIALS_RECHECK)
                continue

            try:
                ok, reason = self.client.ensure_logged_in()
            except pause.ForceStop:          # P (or botctl kill) while logging in
                if not self.exiting:
                    self._idle("operator", "force-stopped during login")
                continue
            self._event("login", ok=ok, reason=reason)
            if not ok:
                self.login_failures += 1
                self.client.kill()
                if self.login_failures >= policy.MAX_LOGIN_FAILURES:
                    self._idle("giving_up", "login")
                else:
                    self._pause_before_retry(self.backoff.next(), after="login failure")
                continue
            self.login_failures = 0

            outcome = self._run_session()
            if self.exiting:
                break
            self.backoff.session_ran(outcome.seconds)
            action = decide(outcome, self.client.logged_in())
            self._event("session_end", final=outcome.final, reason=outcome.reason,
                        seconds=round(outcome.seconds, 1), action=action)
            if action == "restart":
                if not self.budget.allow():
                    self._idle("giving_up", "restart budget")
                else:
                    self._pause_before_retry(self.backoff.next(), after=outcome.final)
            else:
                self._idle(action[len("idle_"):], outcome.reason)
        self._event("supervisor_exit")


def main():
    events.install_excepthooks()
    from lib.bots import discover

    bots = discover(events.ROOT)
    try:
        bot, start = resolve(os.environ.get("BOT"), os.environ.get("LAUNCH"), os.environ.get("VALUE"), bots)
    except ValueError as e:
        events.launcher_error(os.environ.get("BOT"), e, "headless")
        print(f"[headless] {e} — idling (fix docker/.env and restart the container).", file=sys.stderr)
        signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
        while True:
            signal.pause()

    pause.setup(pause_hotkey="o", stop_hotkey="p")     # O/P still work over VNC
    sup = Supervisor(bot, start, RealClient())
    for sig, fn in ((signal.SIGUSR1, sup.on_pause), (signal.SIGUSR2, sup.on_soft_stop),
                    (signal.SIGINT, sup.on_kill), (signal.SIGHUP, sup.on_start),
                    (signal.SIGTERM, sup.on_term)):
        signal.signal(sig, lambda *a, _fn=fn: _fn())
    sup.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
