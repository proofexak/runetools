"""
Unattended mode: keep RuneLite logged in, run one bot, restart it per policy.

    BOT=Tanning LAUNCH="Green Dragonhide" python -m lib.headless
    BOT="Choco Grind" LAUNCH=Run VALUE=500 python -m lib.headless

The container's main command when BOT is set (docker/docker-compose.yml).
Control it from the host with docker/botctl (signals):

    SIGUSR1  pause               SIGUSR2  soft stop → idle    SIGINT  kill → idle
    SIGHUP   resume / start      SIGTERM  force stop and exit

Idle never exits — the container and its VNC stay up for a human to look.
Supervisor events go to log/launcher.jsonl (`python -m lib.logreport supervisor`).
"""
import os, signal, sys, threading, time

import lib.events as events
import lib.live_control as live_control
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

    def missing_templates(self):
        import lib.client as client
        return client.missing_templates(client.load_templates())

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
        pause.set_paused(True)

    def on_soft_stop(self):
        self.operator, self.active = True, False
        self.stats["stop"] = True
        self._wake.set()

    def on_kill(self):
        self.operator, self.active = True, False
        pause.force_stop()
        self._wake.set()

    def on_start(self):
        """Resume a paused bot; if idle, also start it again (fresh budget)."""
        if self.active:
            pause.set_paused(False)
            return
        pause.reset()             # clears pause and a previous kill's force-stop flag
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
            with pause.session():
                self.start(self.stats)
            final, reason, crashed = self.stats.get("step"), self.stats.get("reason"), False
        except Exception as e:
            final, reason, crashed = "crashed", f"{type(e).__name__}: {e}", True
        # P over VNC force-stops too: still set after the session -> operator stop
        operator = self.operator or (pause._force_stop and not crashed)
        return Outcome(final=final, reason=reason, crashed=crashed,
                       operator=operator, seconds=self.clock() - began)

    def _logged_in(self):
        try:
            return self.client.logged_in()
        except Exception:         # can't tell (X/grab error): assume logged out, re-login
            return False

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

            missing = getattr(self.client, "missing_templates", lambda: [])()
            if missing:                      # config problem: don't touch the client
                self._idle("giving_up", f"missing client templates: {', '.join(missing)}")
                continue
            try:
                with pause.session():        # logging in clicks too (live_control's "safe")
                    ok, reason = self.client.ensure_logged_in()
            except pause.ForceStop:          # P (or botctl kill / docker stop) while logging in
                if not self.exiting:
                    self._idle("operator", "force-stopped during login")
                continue
            except Exception as e:           # X/grab/PIL error: a failed login, not a crash
                ok, reason = False, f"{type(e).__name__}: {e}"
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
            if self.exiting:
                break
            if not self.active:              # botctl stop / kill arrived during login
                self._idle("operator", "stopped during login")
                continue

            outcome = self._run_session()
            if self.exiting:
                break
            self.backoff.session_ran(outcome.seconds)
            action = decide(outcome, self._logged_in())
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


def install_signals(sup):
    """botctl's signals -> the supervisor's handlers (see module docstring)."""
    for sig, name in ((signal.SIGUSR1, "on_pause"), (signal.SIGUSR2, "on_soft_stop"),
                      (signal.SIGINT, "on_kill"), (signal.SIGHUP, "on_start"),
                      (signal.SIGTERM, "on_term")):
        signal.signal(sig, lambda signum, frame, _name=name: getattr(sup, _name)())


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
    live_control.start()                               # web app "Take control" (PRO-89)
    sup = Supervisor(bot, start, RealClient())
    install_signals(sup)
    sup.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
