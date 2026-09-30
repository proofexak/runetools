import pytest
from transitions import Machine

import lib.pause as pause
import lib.session as session
from lib.session import run_session, format_elapsed


class _Model:
    pass


def _model():
    m = _Model()
    Machine(model=m, states=["work", "end"], initial="work", auto_transitions=False,
            transitions=[{"trigger": "ok", "source": "work", "dest": "end"},
                         {"trigger": "stop", "source": "work", "dest": "end"}])
    return m


@pytest.fixture
def calls(monkeypatch, tmp_path):
    log = []
    pause.reset()
    monkeypatch.chdir(tmp_path)          # the session's .jsonl lands next to log_prefix
    monkeypatch.setattr(session.log, "setup", lambda prefix, stamp=None: log.append("log"))
    monkeypatch.setattr(session.time, "sleep", lambda s: log.append(f"sleep{s}"))
    real_reset = pause.reset
    monkeypatch.setattr(pause, "reset", lambda: (log.append("reset"), real_reset()))
    yield log
    pause.reset()


def _run(stats, calls, handler=None, setup=None):
    return run_session(
        stats, bot="test", log_prefix="x", intro=["hello"],
        setup=setup or (lambda: calls.append("setup")),
        session=lambda: (calls.append("session"), _model())[1],
        handlers=lambda m: {"work": handler or (lambda: calls.append("work") or "ok")},
        final_states={"end"}, cycle_start="work",
        summary=lambda m, final, last: f"summary {final} {last}",
    )


def test_format_elapsed():
    assert format_elapsed(3725) == "01:02:05"
    assert format_elapsed(0) == "00:00:00"


def test_lifecycle_order(calls):
    stats = {}
    assert _run(stats, calls) == "end"
    assert calls == ["log", "reset", "session", "sleep3", "setup", "work"]
    assert stats["step"] == "end"
    assert stats["start"] is not None


def test_force_stop_during_countdown_skips_setup(calls, monkeypatch):
    def sleep(s):
        calls.append(f"sleep{s}")
        pause.force_stop()          # operator presses P during "Starting in 3s"
    monkeypatch.setattr(session.time, "sleep", sleep)
    stats = {}
    assert _run(stats, calls) == "stopped"
    assert "setup" not in calls and "work" not in calls
    assert stats["step"] == "stopped"


def test_force_stop_from_handler(calls, capsys):
    def boom():
        raise pause.ForceStop()
    assert _run({}, calls, handler=boom) == "stopped"
    out = capsys.readouterr().out
    assert "summary stopped work" in out
    assert "Session ended" in out


def test_stale_stop_flag_cleared(calls):
    stats = {"stop": True, "run": 99}
    _run(stats, calls)
    assert "work" in calls
    assert stats["stop"] is False


def test_intro_and_hint_printed(calls, capsys):
    _run({}, calls)
    out = capsys.readouterr().out
    assert "hello" in out and "Press O to pause, P to force-stop" in out


def test_game_name_in_hint(calls, capsys):
    run_session({}, bot="test", log_prefix="x", intro=[], setup=lambda: None, session=_model,
                handlers=lambda m: {"work": lambda: "ok"}, final_states={"end"},
                cycle_start="work", summary=lambda m, f, l: "", game="the game")
    assert "switch to the game." in capsys.readouterr().out


def _with_teardown(handler, torn):
    return run_session({}, bot="test", log_prefix="x", intro=[], setup=lambda: None, session=_model,
                       handlers=lambda m: {"work": handler}, final_states={"end"},
                       cycle_start="work", summary=lambda m, f, l: "",
                       teardown=lambda: torn.append(1))


def test_teardown_on_normal_end(calls):
    torn = []
    _with_teardown(lambda: "ok", torn)
    assert torn == [1]


def test_teardown_on_force_stop(calls):
    torn = []

    def boom():
        raise pause.ForceStop()
    assert _with_teardown(boom, torn) == "stopped"
    assert torn == [1]


def test_teardown_on_crash_and_crash_propagates(calls):
    torn = []

    def boom():
        raise RuntimeError("bug")
    with pytest.raises(RuntimeError):
        _with_teardown(boom, torn)
    assert torn == [1]


def test_emergency_teardown_runs_active_teardown_once(calls):
    torn = []

    def handler():
        session.emergency_teardown()   # overlay Exit clicked mid-session
        return "ok"
    _with_teardown(handler, torn)
    assert torn == [1]                 # not again in finally
    session.emergency_teardown()       # after the session: nothing active
    assert torn == [1]
