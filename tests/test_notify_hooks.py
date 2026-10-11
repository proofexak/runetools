"""Where phone alerts fire (PRO-93): run_session (menu), the unattended supervisor, EventLog.operator_stop."""
import pytest
from transitions import Machine

import lib.events as events
import lib.headless as headless
import lib.notify as notify
import lib.pause as pause
import lib.session as session
from lib.bots import Bot
from lib.session import run_session
from tests.test_headless import FakeClient, blk, bot_script, make, scheduled, supervisor_events


@pytest.fixture(autouse=True)
def clean_pause():
    pause.reset()
    yield
    pause.reset()


@pytest.fixture
def sent(monkeypatch):
    """Every alert send() was asked for, as (alert, kwargs)."""
    out = []
    monkeypatch.setattr(notify, "send", lambda alert, **kw: out.append((alert, kw)))
    return out


# ── EventLog.operator_stop ────────────────────────────────────────────────────

@pytest.mark.parametrize("event", ["force_stop", "soft_stop"])
def test_operator_stop_set_by_force_and_soft_stop(tmp_path, event):
    log = events.EventLog(str(tmp_path / "s.jsonl"), bot="b", session="s", push=False)
    assert log.operator_stop is False
    log.emit("step", state="a")
    assert log.operator_stop is False
    log.emit(event, state="a")
    assert log.operator_stop is True
    log.close()


def test_operator_stop_even_when_the_log_cannot_be_written(tmp_path):
    log = events.EventLog(str(tmp_path), bot="b", session="s", push=False)   # a directory
    log.emit("force_stop", state="a")
    assert log.operator_stop is True


# ── menu sessions (run_session) ───────────────────────────────────────────────

class _Model:
    pass


def _model(stop_reason=None):
    m = _Model()
    m.stop_reason = stop_reason
    Machine(model=m, states=["a", "done", "stopped"], initial="a", auto_transitions=False,
            transitions=[{"trigger": "ok", "source": "a", "dest": "done"},
                         {"trigger": "fail", "source": "a", "dest": "stopped"},
                         {"trigger": "stop", "source": "a", "dest": "stopped"}])
    return m


@pytest.fixture
def env(monkeypatch, tmp_path):
    pause.reset()
    monkeypatch.setattr(session.time, "sleep", lambda s: None)
    monkeypatch.setattr(session.log, "setup", lambda prefix, stamp=None: None)
    yield tmp_path
    pause.reset()
    events.finish()


def _run(tmp_path, handler, stop_reason=None, stats=None):
    return run_session(
        stats if stats is not None else {}, bot="tanner", params={"hide_type": "green", "start_at": "GE"},
        log_prefix=str(tmp_path / "bot"), intro=[], setup=lambda: None,
        session=lambda: _model(stop_reason), handlers=lambda m: {"a": handler},
        final_states={"done", "stopped"}, cycle_start="a", summary=lambda m, f, l: "")


def test_bot_stop_alerts_once(env, sent, monkeypatch):
    monkeypatch.setenv("RUNETOOLS_ACCOUNT", "Main")
    stats = {}

    def out_of_hides():
        stats["run"] = 4
        return "fail"
    assert _run(env, out_of_hides, stop_reason="out of hides", stats=stats) == "stopped"
    (alert, kw), = sent
    assert (alert.source, alert.bot, alert.account, alert.reason, alert.last_step, alert.runs) == (
        "menu", "tanner", "Main", "out of hides", "a", 4)
    assert alert.launch == "hide_type=green, start_at=GE" and alert.seconds >= 0
    assert stats["last_step"] == "a" and stats["step"] == "stopped"


def test_alert_goes_out_after_session_end(env, monkeypatch):
    seen = []

    def send(alert, **kw):
        import glob, json
        (path,) = glob.glob(str(env / "bot_*.jsonl"))
        seen.append([json.loads(l)["event"] for l in open(path)][-1])
    monkeypatch.setattr(notify, "send", send)
    _run(env, lambda: "fail")
    assert seen == ["session_end"]


def test_crash_alerts_once_and_still_raises(env, sent):
    def boom():
        raise RuntimeError("ellis vanished")
    with pytest.raises(RuntimeError):
        _run(env, boom)
    (alert, _), = sent
    assert alert.reason == "crashed: RuntimeError: ellis vanished" and alert.last_step == "a"


def test_done_sends_nothing(env, sent):
    assert _run(env, lambda: "ok") == "done"
    assert sent == []


def test_force_stop_sends_nothing(env, sent):
    def p_pressed():
        raise pause.ForceStop()
    assert _run(env, p_pressed) == "stopped"
    assert sent == []


def test_overlay_stop_sends_nothing(env, sent, monkeypatch):
    stats = {}
    monkeypatch.setattr(pause, "wait", lambda: stats.update(stop=True))   # Stop clicked
    assert _run(env, lambda: "ok", stop_reason="stopped via overlay", stats=stats) == "stopped"
    assert sent == []


def test_ctrl_c_sends_nothing(env, sent):
    def ctrl_c():
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        _run(env, ctrl_c)
    assert sent == []


def test_supervised_session_sends_nothing(env, sent, monkeypatch):
    monkeypatch.setattr(notify, "supervised", True)
    _run(env, lambda: "fail", stop_reason="out of hides")
    with pytest.raises(RuntimeError):
        _run(env, lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert sent == []


def test_a_failing_sender_never_breaks_the_session(env, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("sender down")
    monkeypatch.setattr(notify, "send", boom)
    assert _run(env, lambda: "fail") == "stopped"


# ── unattended (lib/headless.py) ──────────────────────────────────────────────

def _session(step, reason, last_step="banking", runs=7, seconds=0, clock=None):
    def run(stats):
        stats.update(step=step, reason=reason, last_step=last_step, run=runs)
        if clock is not None:
            clock["t"] += seconds
    return run


def test_giving_up_while_logged_in_alerts_once(tmp_path, sent, monkeypatch):
    monkeypatch.setenv("RUNETOOLS_ACCOUNT", "Main")
    holder = {}
    start, _ = bot_script(lambda stats: _session("stopped", "out of hides", clock=holder["clock"], seconds=125)(stats))
    sup, clock = make(start, FakeClient(logged_in=True))
    holder["clock"] = clock
    sup.launch = "Green Dragonhide"
    sup.run_forever()
    (alert, kw), = sent
    assert (alert.source, alert.account, alert.bot, alert.launch, alert.reason) == (
        "unattended", "Main", "Tanning", "Green Dragonhide", "out of hides")
    assert (alert.last_step, alert.runs, alert.seconds) == ("banking", 7, 125)


@pytest.mark.parametrize("steps", [
    [("done", "all items done")],                                     # finished
    [RuntimeError("boom"), ("done", None)],                           # crash, then a good restart
    [("stopped", "recovery failed"), ("done", None)],                 # stopped while logged out: restart
])
def test_finished_and_restarts_send_nothing(sent, steps):
    start, _ = bot_script(*steps)
    sup, _ = make(start, FakeClient(logged_in=[False, True]))
    sup.run_forever()
    assert sent == []


def test_giving_up_without_a_reason(sent):
    start, _ = bot_script(("stopped", None))
    sup, _ = make(start, FakeClient(logged_in=True))
    sup.run_forever()
    assert sent[0][0].reason == "gave up"


def test_operator_stop_sends_nothing(sent):
    holder = {}

    def session_fn(stats):
        holder["sup"].on_soft_stop()
        stats["step"], stats["reason"] = ("stopped", "stopped via overlay")
    start, _ = bot_script(session_fn)
    sup, _ = make(start, FakeClient())
    holder["sup"] = sup
    sup.run_forever()
    assert sent == []


def test_restart_budget_alerts_once(sent):
    start, _ = bot_script(*[RuntimeError("boom")] * 10)
    sup, _ = make(start, FakeClient())
    sup.run_forever()
    (alert, _), = sent
    assert alert.reason == "restart budget: RuntimeError: boom"      # the last crash, too


def test_missing_templates_alert(sent):
    class Client(FakeClient):
        def missing_templates(self):
            return ["login_play"]
    start, _ = bot_script()
    sup, _ = make(start, Client())
    sup.run_forever()
    (alert, _), = sent
    assert alert.reason == "missing client templates: login_play" and alert.last_step is None


class _OrderedClient(FakeClient):
    def __init__(self, order, **kw):
        super().__init__(**kw)
        self.order = order

    def kill(self):
        super().kill()
        self.order.append("kill")


def test_three_failed_logins_alert_with_a_screenshot_taken_before_the_kill(tmp_path, sent, monkeypatch):
    order = []
    monkeypatch.setattr(notify, "screenshot", lambda: order.append("shot") or b"shot")
    start, _ = bot_script(("done", None))
    client = _OrderedClient(order, logins=[(False, "login screen never appeared")] * 3)
    sup, _ = make(start, client)
    sup.run_forever()
    assert order == ["kill", "kill", "shot", "kill"]
    (alert, kw), = sent
    assert alert.reason == "login: login screen never appeared" and kw["image"] == b"shot"
    idle = [e for e in supervisor_events(tmp_path) if e["event"] == "idle"]
    assert idle[-1]["reason"] == "login"                 # the idle event keeps its reason


def test_credentials_wait_alerts_once_per_wait(sent):
    seen = {"n": 0}

    def creds():
        seen["n"] += 1
        return seen["n"] > 3
    start, calls = bot_script(("done", None))
    sup, clock = make(start, FakeClient(creds=creds))
    sup.run_forever()
    assert clock["sleeps"] == [60, 60, 60] and len(calls) == 1
    (alert, kw), = sent
    assert "credentials" in alert.reason and alert.source == "unattended"


def test_credentials_wait_alerts_again_after_they_came_back_and_went(sent):
    answers = iter([False, False, True, False, True])
    start, _ = bot_script(("stopped", "recovery failed"), ("done", None))
    sup, _ = make(start, FakeClient(creds=lambda: next(answers), logged_in=[False]))
    sup.run_forever()
    assert len(sent) == 2


def test_schedule_one_lost_block_sends_nothing_three_alert(tmp_path, sent, monkeypatch):
    order = []
    monkeypatch.setattr(notify, "screenshot", lambda: order.append("shot") or b"shot")
    start, calls = bot_script(*[("stopped", "GE bank not found")] * 3)
    client = _OrderedClient(order, logged_in=True)
    blocks = [blk(1, 0, 1000), blk(2, 2000, 3000), blk(3, 4000, 5000)]
    sup, clock, _ = scheduled(start, client, blocks)
    sup.run_forever()
    assert len(calls) == 3
    (alert, kw), = sent                                   # not for blocks 1 and 2 (schedule_skip)
    assert "GE bank not found" in alert.reason and "3 blocks" in alert.reason
    assert alert.launch == "Green Dragonhide · Al Kharid" and alert.bot == "Tanning"
    assert kw["image"] == b"shot" and order[-2:] == ["shot", "kill"]
    skips = [e for e in supervisor_events(tmp_path) if e["event"] == "schedule_skip"]
    assert len(skips) == 2


def test_launch_label():
    assert headless.launch_label("Green Dragonhide", "Al Kharid") == "Green Dragonhide · Al Kharid"
    assert headless.launch_label("Run", None) == "Run"
    assert headless.launch_label(None, "") is None


def test_setup_error_alerts(sent, monkeypatch):
    monkeypatch.setenv("RUNETOOLS_ACCOUNT", "Main")
    headless.alert_setup_error(ValueError("unknown BOT 'Nope'"), {"BOT": "Nope", "LAUNCH": "x"})
    (alert, kw), = sent
    assert (alert.bot, alert.launch, alert.reason, alert.source, alert.account) == (
        "Nope", "x", "unknown BOT 'Nope'", "unattended", "Main")
    assert kw == {"screenshot": False}                    # RuneLite isn't up: nothing to see
