"""
Unattended mode: keep RuneLite logged in, run one bot, restart it per policy.

    BOT=Tanning LAUNCH="Green Dragonhide" python -m lib.headless
    BOT="Choco Grind" LAUNCH=Run VALUE=500 python -m lib.headless

The container's main command when BOT is set (docker/docker-compose.yml).
Control it from the host with docker/botctl (signals):

    SIGUSR1  pause               SIGUSR2  soft stop → idle    SIGINT  kill → idle
    SIGHUP   resume / start      SIGTERM  force stop and exit

Schedule mode (SCHEDULE=1, PRO-102) plays only inside the blocks of the account's schedule
(data/schedules/<account>.json, written by the web app — lib/schedule.py): each block names its
own BOT / LAUNCH / VALUE; between blocks RuneLite is closed; at a block's end the bot gets the
soft stop (it finishes its trip), and a kill BLOCK_FORCE_GRACE later if it's still running.

Idle never exits — the container and its VNC stay up for a human to look.
Supervisor events go to log/launcher.jsonl (`python -m lib.logreport supervisor`).
"""
import os, signal, sys, threading, time

import lib.accounts as accounts
import lib.events as events
import lib.live_control as live_control
import lib.pause as pause
import lib.schedule as schedule
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
    if launch.ask_choice:
        prompt, options = launch.ask_choice
        option = next((o for o in options if o.lower() == (value or "").strip().lower()), None)
        if option is None:
            raise ValueError(f"{bot.name} / {launch.label} needs VALUE ({prompt} {', '.join(options)})")
        return bot, (lambda stats: launch.start(stats, option))
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
    WATCH_POLL = 5.0     # s between the block-end watcher's clock checks

    def __init__(self, bot, start, client, clock=time.time, sleeper=None, idle_waiter=None,
                 schedule=None, resolver=None, watcher=None):
        """schedule: () -> (enabled, blocks) turns on schedule mode; resolver: Block ->
        (Bot, start), ValueError for names it doesn't know; watcher(end, soft, force) -> stop,
        end() the block's end as the file says now (default: _watch, a thread)."""
        self.bot, self.start, self.client, self.clock = bot, start, client, clock
        self.schedule, self.resolver = schedule, resolver
        self.watcher = watcher or self._watch
        self._skipped = set()             # block ids not to play (finished early, unknown launch)
        self._client_up = True            # unknown at start: closing it is harmless
        self._playing = self._waiting_for = None
        self._deadline_forced = False
        self._give_ups = 0                # schedule mode: blocks lost in a row
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

    def _run_session(self, block=None):
        self.operator = False
        began = self.clock()
        stop_watch = (self.watcher(lambda: self._block_end(block), self._block_over, self._block_overrun)
                      if block else None)
        try:
            with pause.session():
                self.start(self.stats)
            final, reason, crashed = self.stats.get("step"), self.stats.get("reason"), False
        except Exception as e:
            final, reason, crashed = "crashed", f"{type(e).__name__}: {e}", True
        finally:
            if stop_watch:
                stop_watch()
        # P over VNC force-stops too: still set after the session -> operator stop
        operator = self.operator or (pause._force_stop and not crashed and not self._deadline_forced)
        if self._deadline_forced:          # the block's own kill: the next block must log in again
            self._deadline_forced = False
            pause.reset()
        return Outcome(final=final, reason=reason, crashed=crashed,
                       operator=operator, seconds=self.clock() - began)

    # ── schedule mode ──────────────────────────────────────────────────────────
    def _block_over(self):
        """The block ended: the soft stop — the bot finishes its trip, like the overlay's Stop."""
        self.stats["stop"] = True

    def _block_overrun(self):
        """BLOCK_FORCE_GRACE past the block's end and still running: stop it now."""
        self._deadline_forced = True
        pause.force_stop()

    def _block_end(self, block):
        """The block's end as the schedule says now: moved, or now if it was deleted or the
        schedule switched off — a running block follows edits made in the web app."""
        enabled, blocks = self.schedule()
        same = next((b for b in blocks if b.id == block.id), None) if enabled else None
        return same.end if same else self.clock()

    def _lose_block(self, block, reason):
        """The bot gave up (or couldn't log in) in this block: sit it out, logged out — and after
        MAX_BLOCK_GIVE_UPS in a row, idle: something needs a human, not the next block."""
        self._give_ups += 1
        if self._give_ups < policy.MAX_BLOCK_GIVE_UPS:
            self._skipped.add(block.id)
            self._event("schedule_skip", id=block.id, reason=reason)
            return
        if self._client_up and not pause.is_held():
            self.client.kill()
            self._client_up = False
        self._give_ups = 0
        self._idle("giving_up", f"{reason} ({policy.MAX_BLOCK_GIVE_UPS} blocks in a row)")

    def _watch(self, end, soft, force):
        """Calls soft() once when end() has passed, force() once BLOCK_FORCE_GRACE later — but
        never while a human has the game or paused it (they get to finish). Returns stop()."""
        done = threading.Event()

        def run():
            softened = False
            while not done.wait(self.WATCH_POLL):
                now, until = self.clock(), end()
                if now < until:
                    continue
                if not softened:
                    softened = True
                    soft()
                if now >= until + policy.BLOCK_FORCE_GRACE and not pause.is_held() and not pause.is_paused():
                    force()
                    return
        thread = threading.Thread(target=run, name="block-watch", daemon=True)
        thread.start()

        def stop():
            done.set()
            thread.join(self.WATCH_POLL + 1)
        return stop

    def _schedule_block(self):
        """The block to play now, with self.bot / self.start set from it — or None after
        waiting a while logged out (until the next block, at most SCHEDULE_RECHECK)."""
        enabled, blocks = self.schedule()
        now = self.clock()
        block = schedule.current(blocks, now) if enabled else None
        if block is not None and block.id not in self._skipped:
            try:
                self.bot, self.start = self.resolver(block)
            except ValueError as e:
                self._skipped.add(block.id)
                self._event("schedule_skip", id=block.id, reason=str(e))
            else:
                if self._playing != block.id:
                    self._playing = block.id
                    self._event("schedule_block", id=block.id, launch=block.launch,
                                value=block.value, end=block.end)
                return block
        self._playing = None
        if self._client_up and not pause.is_held():   # nothing to play: logged out (not under a human)
            self.client.kill()
            self._client_up = False
            self._event("schedule_logout")
        if not enabled:
            until, why = None, "schedule disabled or unreadable"
        elif block is not None:
            until, why = block.end, "sitting out this block"
        else:
            until = schedule.next_start(blocks, now)
            why = "between blocks" if until else "no blocks ahead"
        if until != self._waiting_for:
            self._waiting_for = until
            self._event("schedule_wait", next=until, reason=why)
        self._sleep(min(policy.SCHEDULE_RECHECK, max(1, until - now)) if until else policy.SCHEDULE_RECHECK)
        return None

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
            block = None
            if self.schedule is not None:
                block = self._schedule_block()
                if block is None:
                    continue
            if not self.client.credentials_saved():
                self._event("waiting", reason="no saved credentials (~/.runelite/credentials.properties)")
                self._sleep(policy.CREDENTIALS_RECHECK)
                continue

            missing = getattr(self.client, "missing_templates", lambda: [])()
            if missing:                      # config problem: don't touch the client
                self._idle("giving_up", f"missing client templates: {', '.join(missing)}")
                continue
            self._client_up = True
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
                if self.login_failures >= policy.MAX_LOGIN_FAILURES and block is not None:
                    self.login_failures = 0
                    self._lose_block(block, f"login: {reason}")
                elif self.login_failures >= policy.MAX_LOGIN_FAILURES:
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

            outcome = self._run_session(block)
            if self.exiting:
                break
            self.backoff.session_ran(outcome.seconds)
            if block is None:
                action = decide(outcome, self._logged_in())
            else:
                action = policy.schedule_decide(outcome, self._logged_in(), self.clock() >= self._block_end(block))
            self._event("session_end", final=outcome.final, reason=outcome.reason,
                        seconds=round(outcome.seconds, 1), action=action)
            if action == "next_block":
                self._give_ups = 0
                continue
            if action == "skip_block":
                self._give_ups = 0
                self._skipped.add(block.id)
                self._event("schedule_skip", id=block.id, reason=outcome.reason or "finished")
                continue
            if action == "give_up_block":
                self._lose_block(block, outcome.reason or outcome.final)
                continue
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


def setup(env, bots, root=None):
    """(bot, start, extra Supervisor kwargs) from the environment. SCHEDULE=1: the account's
    schedule file names each block's bot (the account: RUNETOOLS_ACCOUNT / data/active_account);
    otherwise BOT / LAUNCH / VALUE. ValueError says what's missing."""
    if env.get("SCHEDULE") == "1":
        account = env.get(accounts.ENV_VAR) or accounts.active()
        if not account:
            raise ValueError("SCHEDULE=1 needs the account (RUNETOOLS_ACCOUNT) to find its schedule")
        path = schedule.path_for(account, root)
        from lib.bots import Bot
        return Bot("schedule", []), None, {
            "schedule": lambda: schedule.load(path),
            "resolver": lambda b: resolve(b.bot, b.launch, b.value, bots)}
    bot, start = resolve(env.get("BOT"), env.get("LAUNCH"), env.get("VALUE"), bots)
    return bot, start, {}


def main():
    events.install_excepthooks()
    from lib.bots import discover

    bots = discover(events.ROOT)
    try:
        bot, start, extra = setup(os.environ, bots)
    except ValueError as e:
        events.launcher_error(os.environ.get("BOT"), e, "headless")
        print(f"[headless] {e} — idling (fix the account file and restart the container).", file=sys.stderr)
        signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
        while True:
            signal.pause()

    pause.setup(pause_hotkey="o", stop_hotkey="p")     # O/P still work over VNC
    live_control.start()                               # web app "Take control" (PRO-89)
    sup = Supervisor(bot, start, RealClient(), **extra)
    install_signals(sup)
    sup.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
