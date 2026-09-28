import pytest
from transitions import Machine, MachineError

import lib.pause as pause
from lib.state_machine import run_machine

FINAL = {"end"}


class _Model:
    pass


def _machine():
    m = _Model()
    Machine(model=m, states=["a", "b", "end"], initial="a", auto_transitions=False,
            transitions=[
                {"trigger": "ok",   "source": "a", "dest": "b"},
                {"trigger": "ok",   "source": "b", "dest": "a"},
                {"trigger": "stop", "source": "a", "dest": "end"},
                {"trigger": "quit", "source": "b", "dest": "end"},
            ])
    return m


@pytest.fixture
def log(monkeypatch):
    calls = []
    monkeypatch.setattr(pause, "wait", lambda: calls.append("wait"))
    return calls


def _scripted(events, log=None, stats=None, on_call=None):
    """Handlers for every state that pop the next event from `events`."""
    def make(state):
        def handler():
            if log is not None:
                log.append(state)
            if on_call:
                on_call(state)
            return events.pop(0)
        return handler
    return {s: make(s) for s in ("a", "b")}


def test_calls_pause_wait_before_each_handler(log):
    m = _machine()
    run_machine(m, _scripted(["ok", "ok", "ok", "quit"], log), {}, FINAL)
    assert log == ["wait", "a", "wait", "b", "wait", "a", "wait", "b"]


def test_stats_step_names_running_state(log):
    m, stats, seen = _machine(), {}, []
    handlers = _scripted(["ok", "quit"], on_call=lambda s: seen.append((s, stats["step"])))
    run_machine(m, handlers, stats, FINAL)
    assert seen == [("a", "a"), ("b", "b")]


def test_returns_final_state(log):
    stats = {}
    assert run_machine(_machine(), _scripted(["ok", "quit"]), stats, FINAL) == "end"
    assert stats["step"] == "b"


def test_undeclared_event_raises_attribute_error(log):
    with pytest.raises(AttributeError):
        run_machine(_machine(), _scripted(["nope"]), {}, FINAL)


def test_invalid_event_for_state_raises_machine_error(log):
    with pytest.raises(MachineError):
        run_machine(_machine(), _scripted(["quit"]), {}, FINAL)


def test_force_stop_from_pause_propagates(monkeypatch):
    called = []

    def boom():
        raise pause.ForceStop()
    monkeypatch.setattr(pause, "wait", boom)
    with pytest.raises(pause.ForceStop):
        run_machine(_machine(), _scripted(["ok"], called), {}, FINAL)
    assert called == []


def test_force_stop_from_handler_propagates(log):
    def boom():
        raise pause.ForceStop()
    with pytest.raises(pause.ForceStop):
        run_machine(_machine(), {"a": boom}, {}, FINAL)


def test_soft_stop_only_at_cycle_start(log):
    stats, calls = {}, []

    def on_call(state):
        if state == "b":
            stats["stop"] = True
    handlers = _scripted(["ok", "ok", "ok"], calls, on_call=on_call)
    assert run_machine(_machine(), handlers, stats, FINAL, cycle_start="a") == "end"
    assert calls == ["a", "b"]
    assert stats["step"] == "b"


def test_soft_stop_ignored_without_cycle_start(log):
    stats, calls = {"stop": True}, []
    run_machine(_machine(), _scripted(["ok", "quit"], calls), stats, FINAL)
    assert calls == ["a", "b"]


def test_guarded_event_with_no_passing_row_raises(log):
    m = _Model()
    m.allowed = False
    Machine(model=m, states=["a", "end"], initial="a", auto_transitions=False,
            transitions=[{"trigger": "go", "source": "a", "dest": "end", "conditions": "allowed"}])
    calls = []
    with pytest.raises(MachineError):
        run_machine(m, {"a": lambda: calls.append("a") or "go"}, {}, FINAL)
    assert calls == ["a"]


def test_stop_clicked_while_paused_at_cycle_start_runs_no_handler(monkeypatch):
    stats, calls = {}, []

    def wait():
        stats["stop"] = True   # operator clicks Stop while the bot sits paused
    monkeypatch.setattr(pause, "wait", wait)
    assert run_machine(_machine(), _scripted(["ok"], calls), stats, FINAL, cycle_start="a") == "end"
    assert calls == []
