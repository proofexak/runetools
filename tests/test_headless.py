"""lib/headless.py supervisor loop with every dependency stubbed (no RuneLite, no sleeping)."""
import json
import sys

import pytest

import lib.events as events
import lib.headless as headless
import lib.pause as pause
from lib.bots import Bot, Launch


@pytest.fixture(autouse=True)
def clean_pause():
    pause.reset()
    yield
    pause.reset()


class FakeClient:
    def __init__(self, logins=None, logged_in=True, creds=True):
        self.logins = list(logins or [])        # results of ensure_logged_in, default ok
        self._logged_in = logged_in             # bool or list consumed per call
        self.creds = creds
        self.kills = 0
        self.login_calls = 0

    def credentials_saved(self):
        return self.creds() if callable(self.creds) else self.creds

    def ensure_logged_in(self):
        self.login_calls += 1
        return self.logins.pop(0) if self.logins else (True, None)

    def logged_in(self):
        if isinstance(self._logged_in, list):
            return self._logged_in.pop(0)
        return self._logged_in

    def kill(self):
        self.kills += 1


def bot_script(*steps):
    """A bot start(stats) that plays one step per session: ("done"|"stopped", reason) or an exception."""
    steps = list(steps)
    calls = []

    def start(stats):
        calls.append(1)
        step = steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        if callable(step):
            return step(stats)
        stats["step"], stats["reason"] = step
    return start, calls


def make(start, client, end_after=None, **schedule_mode):
    """Supervisor with a fake clock; sleeping advances it. The test ends when the
    supervisor goes idle (or after `end_after` sleeps) by sending SIGTERM."""
    clock = {"t": 0.0, "sleeps": []}
    sup = headless.Supervisor(bot=Bot("Tanning", []), start=start, client=client,
                              clock=lambda: clock["t"], sleeper=None, idle_waiter=None, **schedule_mode)

    def sleeper(seconds):
        clock["sleeps"].append(seconds)
        clock["t"] += seconds
        if end_after and len(clock["sleeps"]) >= end_after:
            sup.on_term()

    def idle_waiter():
        clock.setdefault("idles", 0)
        clock["idles"] += 1
        sup.on_term()

    sup._sleep, sup._idle_wait = sleeper, idle_waiter
    return sup, clock


def supervisor_events(tmp_path):
    path = tmp_path / "log" / "launcher.jsonl"
    return [json.loads(l) for l in open(path)] if path.exists() else []


# ── resolve ───────────────────────────────────────────────────────────────────

def _bots():
    return [Bot("Tanning", [Launch("Green Dragonhide", lambda s: "green"),
                            Launch("Black Dragonhide", lambda s, where: where,
                                   ask_choice=("Where are you?", ["Al Kharid", "GE"]))]),
            Bot("Choco Grind", [Launch("Run", lambda s, n: n, ask_int="How many?")])]


def test_resolve_by_name_case_insensitive():
    bot, start = headless.resolve("tanning", "green dragonhide", None, _bots())
    assert bot.name == "Tanning" and start({}) == "green"


def test_resolve_ask_int_needs_value():
    with pytest.raises(ValueError, match="VALUE"):
        headless.resolve("Choco Grind", "Run", None, _bots())
    bot, start = headless.resolve("Choco Grind", "Run", "500", _bots())
    assert start({}) == 500


def test_resolve_ask_choice_takes_one_of_the_options():
    bot, start = headless.resolve("Tanning", "Black Dragonhide", "ge", _bots())
    assert start({}) == "GE"                           # the option's own spelling
    for value in (None, "Varrock"):
        with pytest.raises(ValueError, match="Al Kharid, GE"):
            headless.resolve("Tanning", "Black Dragonhide", value, _bots())


@pytest.mark.parametrize("bot,launch,msg", [("Nope", "x", "Tanning"), ("Tanning", "Blue", "Green Dragonhide")])
def test_resolve_unknown_names_list_the_choices(bot, launch, msg):
    with pytest.raises(ValueError, match=msg):
        headless.resolve(bot, launch, None, _bots())


# ── policy in the loop ────────────────────────────────────────────────────────

def test_crash_restarts_with_backoff(tmp_path):
    start, calls = bot_script(RuntimeError("boom"), RuntimeError("boom"), ("done", None))
    sup, clock = make(start, FakeClient())
    sup.run_forever()
    assert len(calls) == 3 and clock["sleeps"] == [30, 60]
    kinds = [e["event"] for e in supervisor_events(tmp_path)]
    assert kinds.count("restart") == 2 and "idle" in kinds


def test_stop_while_logged_out_relogs_and_restarts():
    start, calls = bot_script(("stopped", "recovery failed"), ("done", None))
    sup, _ = make(start, FakeClient(logged_in=[False, True]))
    sup.run_forever()
    assert len(calls) == 2


def test_stop_while_logged_in_goes_idle_giving_up(tmp_path):
    start, calls = bot_script(("stopped", "no glory charges left to recover"))
    sup, clock = make(start, FakeClient(logged_in=True))
    sup.run_forever()
    assert len(calls) == 1 and clock["idles"] == 1
    idle = [e for e in supervisor_events(tmp_path) if e["event"] == "idle"][-1]
    assert idle["why"] == "giving_up" and "glory" in idle["reason"]


def test_done_goes_idle_finished(tmp_path):
    start, _ = bot_script(("done", "all items done"))
    sup, _ = make(start, FakeClient())
    sup.run_forever()
    assert [e for e in supervisor_events(tmp_path) if e["event"] == "idle"][-1]["why"] == "finished"


def test_restart_budget_exhausted_goes_idle(tmp_path):
    start, calls = bot_script(*[RuntimeError("boom")] * 10)
    sup, _ = make(start, FakeClient())
    sup.run_forever()
    assert len(calls) == 6                          # first run + 5 restarts
    assert [e for e in supervisor_events(tmp_path) if e["event"] == "idle"][-1]["reason"] == "restart budget"


def test_three_login_failures_go_idle(tmp_path):
    start, calls = bot_script(("done", None))
    client = FakeClient(logins=[(False, "login screen never appeared")] * 3)
    sup, clock = make(start, client)
    sup.run_forever()
    assert calls == [] and client.kills == 3 and clock["sleeps"] == [30, 60]
    assert [e for e in supervisor_events(tmp_path) if e["event"] == "idle"][-1]["reason"] == "login"


def test_waits_for_saved_credentials(tmp_path):
    seen = {"n": 0}

    def creds():
        seen["n"] += 1
        return seen["n"] > 2
    start, calls = bot_script(("done", None))
    sup, clock = make(start, FakeClient(creds=creds))
    sup.run_forever()
    assert clock["sleeps"] == [60, 60] and len(calls) == 1
    waits = [e for e in supervisor_events(tmp_path) if e["event"] == "waiting"]
    assert len(waits) == 2 and "credentials" in waits[0]["reason"]


# ── signals ───────────────────────────────────────────────────────────────────

def test_soft_stop_during_session_goes_idle_operator(tmp_path):
    holder = {}

    def session(stats):
        holder["sup"].on_soft_stop()            # botctl stop while the bot runs
        assert stats["stop"] is True
        stats["step"], stats["reason"] = ("stopped", "stopped via overlay")
    start, _ = bot_script(session)
    sup, _ = make(start, FakeClient())
    holder["sup"] = sup
    sup.run_forever()
    assert [e for e in supervisor_events(tmp_path) if e["event"] == "idle"][-1]["why"] == "operator"


def test_kill_force_stops_and_goes_idle(tmp_path):
    holder = {}

    def session(stats):
        holder["sup"].on_kill()
        assert pause._force_stop is True
        stats["step"], stats["reason"] = ("stopped", "force-stopped (P)")
    start, _ = bot_script(session)
    sup, _ = make(start, FakeClient())
    holder["sup"] = sup
    sup.run_forever()
    assert [e for e in supervisor_events(tmp_path) if e["event"] == "idle"][-1]["why"] == "operator"


def test_start_signal_leaves_idle_and_resets_budget():
    start, calls = bot_script(("done", None), ("done", None))
    sup, clock = make(start, FakeClient())
    idles = {"n": 0}

    def idle_waiter():
        idles["n"] += 1
        if idles["n"] == 1:
            sup.on_start()                       # botctl start
        else:
            sup.on_term()
    sup._idle_wait = idle_waiter
    sup.run_forever()
    assert len(calls) == 2


def test_start_signal_during_backoff_skips_the_rest_of_it():
    start, calls = bot_script(RuntimeError("boom"), ("done", None))
    sup, clock = make(start, FakeClient())

    def sleeper(seconds):
        clock["sleeps"].append(seconds)
        sup.on_start()                           # arrives mid-backoff
    sup._sleep = sleeper
    sup.run_forever()
    assert len(calls) == 2


def test_term_signal_returns(tmp_path):
    holder = {}

    def session(stats):
        holder["sup"].on_term()
        assert pause._force_stop is True
        stats["step"], stats["reason"] = ("stopped", "force-stopped (P)")
    start, calls = bot_script(session, ("done", None))
    sup, _ = make(start, FakeClient())
    holder["sup"] = sup
    sup.run_forever()
    assert len(calls) == 1
    assert supervisor_events(tmp_path)[-1]["event"] == "supervisor_exit"


def test_pause_signal_pauses():
    sup, _ = make(bot_script()[0], FakeClient())
    sup.on_pause()
    assert pause.is_paused()


def test_launcher_event_common_fields(tmp_path):
    events.launcher_event("Tanning", "restart", attempt=2, delay=60)
    (rec,) = supervisor_events(tmp_path)
    assert rec["bot"] == "Tanning" and rec["event"] == "restart" and rec["session"] is None
    assert rec["attempt"] == 2 and "ts" in rec


class LoginGatedClient(FakeClient):
    """ensure_logged_in goes through the real pause gate, like lib.client does."""
    def ensure_logged_in(self):
        pause.wait()
        return super().ensure_logged_in()


def test_start_after_kill_can_log_in_again():
    holder, idles = {}, {"n": 0}

    def killed_session(stats):
        holder["sup"].on_kill()
        stats["step"], stats["reason"] = ("stopped", "force-stopped (P)")
    start, calls = bot_script(killed_session, ("done", None))
    sup, _ = make(start, LoginGatedClient())
    holder["sup"] = sup

    def idle_waiter():
        idles["n"] += 1
        sup.on_start() if idles["n"] == 1 else sup.on_term()
    sup._idle_wait = idle_waiter
    sup.run_forever()
    assert len(calls) == 2


def test_force_stop_during_login_goes_idle(tmp_path):
    class PressesP(FakeClient):
        def ensure_logged_in(self):
            pause.force_stop()             # P pressed over VNC while logging in
            pause.wait()
    start, calls = bot_script(("done", None))
    sup, clock = make(start, PressesP())
    sup.run_forever()
    assert calls == [] and clock["idles"] == 1
    assert [e for e in supervisor_events(tmp_path) if e["event"] == "idle"][-1]["why"] == "operator"


@pytest.mark.skipif(sys.platform == "win32", reason="SIGUSR1/SIGUSR2/SIGHUP are POSIX-only: the supervisor "
                    "runs in the Linux container")
def test_install_signals_maps_each_signal(monkeypatch):
    import signal
    installed = {}
    monkeypatch.setattr(signal, "signal", lambda sig, fn: installed.__setitem__(sig, fn))
    sup, _ = make(bot_script()[0], FakeClient())
    called = []
    for name in ("on_pause", "on_soft_stop", "on_kill", "on_start", "on_term"):
        monkeypatch.setattr(sup, name, lambda n=name: called.append(n))
    headless.install_signals(sup)
    for sig in (signal.SIGUSR1, signal.SIGUSR2, signal.SIGINT, signal.SIGHUP, signal.SIGTERM):
        installed[sig](sig, None)
    assert called == ["on_pause", "on_soft_stop", "on_kill", "on_start", "on_term"]


# ── review fixes ──────────────────────────────────────────────────────────────

def test_soft_stop_during_login_does_not_start_a_session(tmp_path):
    holder = {}

    class StopsDuringLogin(FakeClient):
        def ensure_logged_in(self):
            holder["sup"].on_soft_stop()         # botctl stop while logging in
            return True, None
    start, calls = bot_script(("done", None))
    sup, _ = make(start, StopsDuringLogin())
    holder["sup"] = sup
    sup.run_forever()
    assert calls == []
    assert [e for e in supervisor_events(tmp_path) if e["event"] == "idle"][-1]["why"] == "operator"


def test_term_during_login_exits_without_running_the_bot(tmp_path):
    holder = {}

    class TermDuringLogin(FakeClient):
        def ensure_logged_in(self):
            holder["sup"].on_term()
            return True, None                    # e.g. already in game: no gate passed
    start, calls = bot_script(("done", None))
    sup, _ = make(start, TermDuringLogin())
    holder["sup"] = sup
    sup.run_forever()
    assert calls == [] and supervisor_events(tmp_path)[-1]["event"] == "supervisor_exit"


def test_p_over_vnc_counts_as_operator_stop(tmp_path):
    def p_pressed(stats):
        pause.force_stop()                       # P via VNC, not botctl
        stats["step"], stats["reason"] = ("stopped", None)
    start, _ = bot_script(p_pressed)
    sup, _ = make(start, FakeClient(logged_in=False))
    sup.run_forever()
    assert [e for e in supervisor_events(tmp_path) if e["event"] == "idle"][-1]["why"] == "operator"


def test_unexpected_login_error_is_a_login_failure_not_a_crash():
    class Explodes(FakeClient):
        def ensure_logged_in(self):
            raise OSError("X connection broke")
    start, calls = bot_script(("done", None))
    client = Explodes()
    sup, _ = make(start, client)
    sup.run_forever()                            # must not raise
    assert calls == [] and client.kills == 3


def test_logged_in_check_error_is_treated_as_logged_out():
    class FlakyCheck(FakeClient):
        def logged_in(self):
            raise OSError("grab failed")
    start, calls = bot_script(("stopped", "recovery failed"), ("done", None))
    sup, _ = make(start, FlakyCheck())
    sup.run_forever()
    assert len(calls) == 2                       # treated as logged out -> relogin + restart


def test_missing_templates_idle_without_killing_the_client(tmp_path):
    class NoTemplates(FakeClient):
        def missing_templates(self):
            return ["login_play", "in_game"]
    start, calls = bot_script(("done", None))
    client = NoTemplates()
    sup, _ = make(start, client)
    sup.run_forever()
    assert calls == [] and client.kills == 0
    idle = [e for e in supervisor_events(tmp_path) if e["event"] == "idle"][-1]
    assert idle["why"] == "giving_up" and "login_play" in idle["reason"]


def test_pause_is_idempotent_and_start_resumes():
    sup, _ = make(bot_script()[0], FakeClient())
    sup.on_pause(); sup.on_pause()
    assert pause.is_paused()                     # pausing twice stays paused
    sup.on_start()
    assert not pause.is_paused()


def test_start_while_running_only_resumes():
    sup, _ = make(bot_script()[0], FakeClient())
    sup.budget.allow()
    sup.on_pause()
    sup.on_start()                               # active: just resume, keep budget/backoff
    assert not pause.is_paused() and len(sup.budget._times) == 1 and not sup._wake.is_set()


# ── schedule mode (PRO-102) ───────────────────────────────────────────────────

from lib.schedule import Block


def blk(id, start, end, launch="Green Dragonhide"):
    return Block(id, start, end, "Tanning", launch, "Al Kharid")


class FakeWatcher:
    """watcher(end, soft, force) → stop: records each block's end; the test fires soft / force."""
    def __init__(self):
        self.ends, self.soft, self.force, self.stops = [], None, None, 0

    def __call__(self, end, soft, force):
        self.ends.append(end)
        self.soft, self.force = soft, force

        def stop():
            self.stops += 1
        return stop


def scheduled(start, client, blocks, end_after=None, enabled=True, resolver=None, t0=0.0):
    """A schedule-mode Supervisor; `blocks` is a list, or a function returning one per read."""
    watcher = FakeWatcher()
    read = blocks if callable(blocks) else (lambda: blocks)
    sup, clock = make(start, client, end_after=end_after, schedule=lambda: (enabled, read()),
                      resolver=resolver or (lambda b: (Bot(b.bot, []), start)), watcher=watcher)
    clock["t"] = t0
    return sup, clock, watcher


def kinds(tmp_path, *names):
    return [e["event"] for e in supervisor_events(tmp_path) if e["event"] in names]


def test_waits_logged_out_until_the_block(tmp_path):
    holder = {}

    def session(stats):
        holder["at"] = holder["clock"]["t"]
        holder["sup"].on_term()
        stats["step"], stats["reason"] = ("stopped", None)
    start, calls = bot_script(session)
    client = FakeClient()
    sup, clock, watcher = scheduled(start, client, [blk(1, 1000, 2000)])
    holder.update(sup=sup, clock=clock)
    sup.run_forever()
    assert client.kills == 1                                 # whatever was up is closed first
    assert clock["sleeps"] == [60] * 16 + [40]               # rechecks, landing on the start
    assert holder["at"] == 1000 and watcher.ends == [2000] and len(calls) == 1
    assert kinds(tmp_path, "schedule_logout", "schedule_wait", "schedule_block") == \
        ["schedule_logout", "schedule_wait", "schedule_block"]


def test_starts_mid_block():
    holder = {}

    def session(stats):
        holder["sup"].on_term()
        stats["step"], stats["reason"] = ("stopped", None)
    start, calls = bot_script(session)
    client = FakeClient()
    sup, clock, watcher = scheduled(start, client, [blk(1, 1000, 3000)], t0=1500)
    holder["sup"] = sup
    sup.run_forever()
    assert clock["sleeps"] == [] and len(calls) == 1 and client.kills == 0 and watcher.ends == [3000]


def test_soft_stop_at_block_end_moves_on(tmp_path):
    holder = {}

    def session(stats):
        holder["watcher"].soft()                 # the block's end arrives mid-trip
        assert stats["stop"] is True
        holder["clock"]["t"] = 2001
        stats["step"], stats["reason"] = ("stopped", "stopped via overlay")
    start, calls = bot_script(session)
    client = FakeClient()
    sup, clock, watcher = scheduled(start, client, [blk(1, 1000, 2000)], end_after=1, t0=1500)
    holder.update(watcher=watcher, clock=clock)
    sup.run_forever()
    assert len(calls) == 1 and client.kills == 1 and watcher.stops == 1
    assert kinds(tmp_path, "schedule_block", "schedule_logout", "idle") == ["schedule_block", "schedule_logout"]


def test_forced_after_grace_is_not_operator(tmp_path):
    holder = {}

    def session(stats):
        holder["watcher"].force()                # ignored the soft stop for 20 min
        assert pause._force_stop is True
        holder["clock"]["t"] = 2000 + 1201
        stats["step"], stats["reason"] = ("stopped", None)   # what run_session reports on ForceStop
    start, calls = bot_script(session)
    sup, clock, watcher = scheduled(start, FakeClient(), [blk(1, 1000, 2000)], t0=1500)
    holder.update(watcher=watcher, clock=clock)
    flags = []

    def sleeper(seconds):                        # the wait after the block
        flags.append(pause._force_stop)
        sup.on_term()
    sup._sleep = sleeper
    sup.run_forever()
    assert kinds(tmp_path, "idle") == [] and "schedule_logout" in kinds(tmp_path, "schedule_logout")
    assert flags == [False]                      # cleared: the next block can log in


def test_unknown_launch_skips_block(tmp_path):
    def resolver(b):
        raise ValueError("unknown LAUNCH 'Purple' for Tanning")
    start, calls = bot_script()
    client = FakeClient()
    sup, clock, _ = scheduled(start, client, [blk(1, 0, 500)], end_after=3, resolver=resolver)
    sup.run_forever()
    assert calls == [] and client.login_calls == 0
    assert kinds(tmp_path, "schedule_skip", "idle") == ["schedule_skip"]
    assert clock["sleeps"] == [60, 60, 60]


def test_done_skips_rest_of_block(tmp_path):
    holder = {}

    def second(stats):
        holder["at"] = holder["clock"]["t"]
        holder["sup"].on_term()
        stats["step"], stats["reason"] = ("stopped", None)
    start, calls = bot_script(("done", "nothing left to tan"), second)
    sup, clock, _ = scheduled(start, FakeClient(), [blk(1, 0, 1000), blk(2, 2000, 3000)])
    holder.update(sup=sup, clock=clock)
    sup.run_forever()
    assert len(calls) == 2 and holder["at"] == 2000
    assert kinds(tmp_path, "schedule_skip", "idle") == ["schedule_skip"]


def test_disabled_schedule_never_logs_in():
    start, calls = bot_script()
    client = FakeClient()
    sup, clock, _ = scheduled(start, client, [blk(1, 0, 5000)], end_after=3, enabled=False)
    sup.run_forever()
    assert client.login_calls == 0 and client.kills == 1 and clock["sleeps"] == [60, 60, 60]


def test_file_change_picked_up():
    reads = {"n": 0}

    def blocks():
        reads["n"] += 1
        return [] if reads["n"] == 1 else [blk(1, 0, 5000)]
    holder = {}

    def session(stats):
        holder["sup"].on_term()
        stats["step"], stats["reason"] = ("stopped", None)
    start, calls = bot_script(session)
    sup, clock, _ = scheduled(start, FakeClient(), blocks)
    holder["sup"] = sup
    sup.run_forever()
    assert clock["sleeps"] == [60] and len(calls) == 1


def test_default_watcher_soft_then_force():
    now = {"t": 0.0}
    sup = headless.Supervisor(bot=Bot("x", []), start=None, client=FakeClient(), clock=lambda: now["t"])
    sup.WATCH_POLL = 0.01
    fired = []
    stop = sup._watch(100, lambda: fired.append("soft"), lambda: fired.append("force"))
    import time
    for t, want in ((50, []), (100, ["soft"]), (1299, ["soft"]), (1300, ["soft", "force"])):
        now["t"] = t
        time.sleep(0.1)
        assert fired == want
    stop()


def test_setup_from_env_schedule_mode(tmp_path):
    (tmp_path / "data" / "schedules").mkdir(parents=True)
    (tmp_path / "data" / "schedules" / "alt1.json").write_text(json.dumps(
        {"enabled": True, "blocks": [{"id": 7, "start": 0, "end": 10, "bot": "Tanning",
                                      "launch": "Black Dragonhide", "value": "GE"}]}))
    bot, start, extra = headless.setup({"SCHEDULE": "1", "RUNETOOLS_ACCOUNT": "alt1"}, _bots(), str(tmp_path))
    enabled, blocks = extra["schedule"]()
    assert enabled and blocks[0].id == 7
    rbot, rstart = extra["resolver"](blocks[0])
    assert rbot.name == "Tanning" and rstart({}) == "GE"


def test_setup_from_env_needs_an_account_in_schedule_mode(monkeypatch):
    monkeypatch.delenv("RUNETOOLS_ACCOUNT", raising=False)
    monkeypatch.setattr(headless.accounts, "active", lambda: None)
    with pytest.raises(ValueError, match="RUNETOOLS_ACCOUNT"):
        headless.setup({"SCHEDULE": "1"}, _bots())


def test_setup_from_env_plain_mode():
    bot, start, extra = headless.setup({"BOT": "Tanning", "LAUNCH": "Green Dragonhide"}, _bots())
    assert bot.name == "Tanning" and start({}) == "green" and extra == {}
