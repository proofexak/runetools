"""Structured events written by run_session / run_machine (PRO-15)."""
import glob
import json
import time

import pytest
from transitions import Machine

import lib.events as events
import lib.pause as pause
import lib.session as session
from lib.session import run_session


class _Model:
    pass


def _model(stop_reason=None):
    m = _Model()
    if stop_reason:
        m.stop_reason = stop_reason
    Machine(model=m, states=["a", "b", "end"], initial="a", auto_transitions=False,
            transitions=[{"trigger": "ok", "source": "a", "dest": "b"},
                         {"trigger": "ok", "source": "b", "dest": "end"},
                         {"trigger": "stop", "source": "a", "dest": "end"}])
    return m


@pytest.fixture
def env(monkeypatch, tmp_path):
    pause.reset()
    monkeypatch.setattr(session.time, "sleep", lambda s: None)
    monkeypatch.setattr(session.log, "setup", lambda prefix, stamp=None: None)
    yield tmp_path
    pause.reset()
    events.finish()


def _events(tmp_path):
    (path,) = glob.glob(str(tmp_path / "bot_*.jsonl"))
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def _run(tmp_path, handlers, session_fn=_model, setup=lambda: None, teardown=None, stats=None):
    return run_session(
        stats if stats is not None else {}, bot="demo", params={"hide_type": "green"},
        log_prefix=str(tmp_path / "bot"), intro=[], setup=setup, session=session_fn,
        handlers=lambda m: handlers, final_states={"end"}, cycle_start="a",
        summary=lambda m, f, l: "", teardown=teardown)


def _counting(stats):
    def step():
        stats["run"] = stats.get("run", 0) + 1
        return "ok"
    return step


def test_normal_session(env):
    stats = {}
    assert _run(env, {"a": _counting(stats), "b": lambda: "ok"}, stats=stats) == "end"
    ev = _events(env)
    assert [e["event"] for e in ev] == ["session_start", "step", "step", "session_end"]
    assert all({"ts", "session", "bot", "event"} <= set(e) for e in ev)
    assert ev[0]["bot"] == "demo" and ev[0]["params"] == {"hide_type": "green"} and "pid" in ev[0]
    assert ev[1]["state"] == "a" and ev[1]["result"] == "ok" and ev[1]["run"] == 1
    assert ev[1]["seconds"] >= 0
    end = ev[-1]
    assert end["final"] == "end" and end["last_step"] == "b" and end["stats"]["run"] == 1
    assert end["paused_seconds"] == 0 and end["active_seconds"] >= 0
    assert events.current() is None


def test_jsonl_shares_the_text_log_stamp(env, monkeypatch):
    stamps = []
    monkeypatch.setattr(session.log, "setup", lambda prefix, stamp=None: stamps.append(stamp))
    _run(env, {"a": lambda: "ok", "b": lambda: "ok"})
    (path,) = glob.glob(str(env / "bot_*.jsonl"))
    assert path.endswith(f"bot_{stamps[0]}.jsonl") and _events(env)[0]["session"] == stamps[0]


def test_pause_is_recorded(env, monkeypatch):
    calls = {"n": 0}

    def wait():
        calls["n"] += 1
        if calls["n"] == 2:          # 1 = countdown gate, 2 = gate before state "a"
            until = time.time() + 0.05    # time.sleep is stubbed out by the fixture
            while time.time() < until:
                pass
            return True
        return False
    monkeypatch.setattr(pause, "wait", wait)
    _run(env, {"a": lambda: "ok", "b": lambda: "ok"})
    ev = _events(env)
    (p,) = [e for e in ev if e["event"] == "pause"]
    assert p["state"] == "a" and p["seconds"] >= 0.05
    assert ev[-1]["paused_seconds"] >= 0.05


def test_soft_stop_is_recorded(env, monkeypatch):
    stats = {}
    monkeypatch.setattr(pause, "wait", lambda: stats.update(stop=True))   # Stop clicked after start
    assert _run(env, {"a": lambda: "ok"}, stats=stats) == "end"
    ev = _events(env)
    assert [e["event"] for e in ev] == ["session_start", "soft_stop", "session_end"]


def test_force_stop_is_recorded_not_raised(env):
    def boom():
        raise pause.ForceStop()
    assert _run(env, {"a": boom}) == "stopped"
    ev = _events(env)
    assert ev[-2]["event"] == "force_stop" and ev[-2]["state"] == "a"
    assert ev[-1]["event"] == "session_end" and ev[-1]["final"] == "stopped"


def test_handler_crash_logged_then_reraised(env):
    def boom():
        raise RuntimeError("ellis vanished")
    with pytest.raises(RuntimeError) as info:
        _run(env, {"a": boom})
    ev = _events(env)
    err, end = ev[-2], ev[-1]
    assert err["event"] == "error" and err["where"] == "session" and err["state"] == "a"
    assert err["type"] == "RuntimeError" and "ellis vanished" in err["traceback"]
    assert end["event"] == "session_end" and end["final"] == "crashed" and end["last_step"] == "a"
    assert events.was_logged(info.value) and events.current() is None


def test_crash_while_building_the_model(env):
    def build():
        raise ValueError("bad config")
    with pytest.raises(ValueError):
        _run(env, {}, session_fn=build)
    end = _events(env)[-1]
    assert end["final"] == "crashed" and end["last_step"] == "starting"


def test_crash_in_setup(env):
    def setup():
        raise OSError("no compass")
    with pytest.raises(OSError):
        _run(env, {}, setup=setup)
    assert _events(env)[-1]["final"] == "crashed"


def test_teardown_crash_does_not_mask_handler_crash(env):
    def boom():
        raise RuntimeError("handler")

    def bad_teardown():
        raise OSError("teardown")
    with pytest.raises(RuntimeError):
        _run(env, {"a": boom}, teardown=bad_teardown)
    errors = [e for e in _events(env) if e["event"] == "error"]
    assert [(e["where"], e["type"]) for e in errors] == [("session", "RuntimeError"), ("teardown", "OSError")]
    assert _events(env)[-1]["final"] == "crashed"


def test_teardown_crash_alone_is_a_crash(env):
    def bad_teardown():
        raise OSError("teardown")
    with pytest.raises(OSError):
        _run(env, {"a": lambda: "ok", "b": lambda: "ok"}, teardown=bad_teardown)
    ev = _events(env)
    assert ev[-2]["where"] == "teardown" and ev[-1]["final"] == "crashed"


def test_keyboard_interrupt_is_interrupted(env):
    def ctrl_c():
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        _run(env, {"a": ctrl_c})
    assert _events(env)[-1]["final"] == "interrupted"


def test_stop_reason_recorded(env):
    _run(env, {"a": lambda: "ok", "b": lambda: "ok"}, session_fn=lambda: _model("GE restock failed"))
    assert _events(env)[-1]["reason"] == "GE restock failed"
