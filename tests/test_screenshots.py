"""Failure screenshots (PRO-91): lib/screenshots.py and its wiring into run_machine / run_session."""
import glob
import json
import os
import types

import numpy as np
import pytest
from PIL import Image
from transitions import Machine

import lib.events as events
import lib.pause as pause
import lib.screenshots as screenshots
import lib.session as session
import lib.vision as vision
from lib.session import run_session
from tests.fakescreen import canvas


class _Model:
    pass


def _model():
    m = _Model()
    Machine(model=m, states=["a", "b", "end"], initial="a", auto_transitions=False,
            transitions=[{"trigger": "ok", "source": "a", "dest": "b"},
                         {"trigger": "fail", "source": "a", "dest": "a"},
                         {"trigger": "not_found", "source": "a", "dest": "a"},
                         {"trigger": "full", "source": "a", "dest": "b"},
                         {"trigger": "ok", "source": "b", "dest": "end"},
                         {"trigger": "fail", "source": "b", "dest": "end"},
                         {"trigger": "stop", "source": "a", "dest": "end"}])
    return m


@pytest.fixture
def env(monkeypatch, tmp_path, fake_screen):
    pause.reset()
    monkeypatch.setattr(session.time, "sleep", lambda s: None)
    monkeypatch.setattr(session.log, "setup", lambda prefix, stamp=None: None)
    fake_screen.show(canvas(400, 400, (20, 20, 20)))
    yield tmp_path
    pause.reset()
    events.finish()
    screenshots.finish()


def _events(tmp_path):
    (path,) = glob.glob(str(tmp_path / "bot_*.jsonl"))
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def _script(results):
    results = list(results)
    return lambda: results.pop(0)


def _run(tmp_path, handlers, marks=None, setup=lambda: None):
    return run_session(
        {}, bot="demo", log_prefix=str(tmp_path / "bot"), intro=[], setup=setup, session=_model,
        handlers=lambda m: handlers, final_states={"end"}, cycle_start=None,
        summary=lambda m, f, l: "", marks=marks)


def _pngs(tmp_path):
    return sorted(os.path.basename(p) for p in glob.glob(str(tmp_path / "*.png")))


# ── run_machine: failing steps ────────────────────────────────────────────────

def test_failed_step_saves_a_png_and_names_it(env):
    _run(env, {"a": _script(["fail", "ok"]), "b": lambda: "ok"})
    ev = _events(env)
    stamp = ev[0]["session"]
    steps = [e for e in ev if e["event"] == "step"]
    assert steps[0]["result"] == "fail"
    assert steps[0]["screenshot"] == f"bot_{stamp}_1_a.png"
    assert "screenshot" not in steps[1] and "screenshot" not in steps[2]
    assert _pngs(env) == [f"bot_{stamp}_1_a.png"]
    img = Image.open(env / f"bot_{stamp}_1_a.png")
    assert img.size == (400, 400)


def test_not_found_counts_too_and_numbers_go_up(env):
    _run(env, {"a": _script(["fail", "not_found", "ok"]), "b": lambda: "ok"})
    shots = [e["screenshot"] for e in _events(env) if e.get("screenshot")]
    assert [s.rsplit("_", 2)[-2] for s in shots] == ["1", "2"]
    assert len(_pngs(env)) == 2


def test_routing_results_take_no_screenshot(env):
    _run(env, {"a": _script(["full"]), "b": lambda: "ok"})
    assert not any("screenshot" in e for e in _events(env))
    assert _pngs(env) == []


def test_cap_per_session(env, monkeypatch):
    monkeypatch.setattr(screenshots, "MAX_PER_SESSION", 2)
    _run(env, {"a": _script(["fail", "fail", "fail", "ok"]), "b": lambda: "ok"})
    fails = [e for e in _events(env) if e["event"] == "step" and e["result"] == "fail"]
    assert ["screenshot" in e for e in fails] == [True, True, False]
    assert len(_pngs(env)) == 2


def test_cap_per_state_keeps_room_for_other_failures(env, monkeypatch):
    # a routine "not_found" loop (a vein, a rock) must not use up the session's screenshots
    monkeypatch.setattr(screenshots, "MAX_PER_STATE", 2)
    _run(env, {"a": _script(["not_found"] * 4 + ["ok"]), "b": _script(["fail"])})
    shots = [(e["state"], "screenshot" in e) for e in _events(env) if e["event"] == "step" and e["result"] != "ok"]
    assert shots == [("a", True), ("a", True), ("a", False), ("a", False), ("b", True)]


def test_error_screenshot_ignores_the_caps(env, monkeypatch):
    monkeypatch.setattr(screenshots, "MAX_PER_SESSION", 1)
    results = ["fail"]

    def a():
        if results:
            return results.pop()
        raise RuntimeError("boom")
    with pytest.raises(RuntimeError):
        _run(env, {"a": a})
    err = next(e for e in _events(env) if e["event"] == "error")
    assert err["screenshot"].endswith("_2_a.png") and len(_pngs(env)) == 2


def test_grab_failure_never_stops_the_bot(env, monkeypatch):
    def broken():
        raise OSError("no display")
    monkeypatch.setattr(screenshots, "grab_screen", broken)
    assert _run(env, {"a": _script(["fail", "ok"]), "b": lambda: "ok"}) == "end"
    steps = [e for e in _events(env) if e["event"] == "step"]
    assert steps[0]["result"] == "fail" and "screenshot" not in steps[0]
    assert _pngs(env) == []


def test_marks_of_the_failing_state_are_drawn(env):
    marks = screenshots.config_marks({"a": ["ELLIS_REGION"], "b": ["BANK_REGION"]},
                                     types.SimpleNamespace(ELLIS_REGION=(10, 60, 50, 30), BANK_REGION=(200, 200, 40, 40)))
    _run(env, {"a": _script(["fail", "ok"]), "b": lambda: "ok"}, marks=marks)
    (name,) = _pngs(env)
    rgb = np.array(Image.open(env / name).convert("RGB"))
    assert tuple(rgb[60, 30]) == vision.MARK_COLORS[0]        # ELLIS_REGION's top edge
    assert tuple(rgb[200, 220]) == (20, 20, 20)               # state b's region isn't drawn


def test_marks_that_raise_still_give_a_screenshot(env):
    def marks(state):
        raise KeyError(state)
    _run(env, {"a": _script(["fail", "ok"]), "b": lambda: "ok"}, marks=marks)
    assert len(_pngs(env)) == 1


# ── run_session: errors ───────────────────────────────────────────────────────

def test_handler_crash_error_event_has_a_screenshot(env):
    def boom():
        raise RuntimeError("ellis vanished")
    with pytest.raises(RuntimeError):
        _run(env, {"a": boom})
    err = next(e for e in _events(env) if e["event"] == "error")
    assert err["screenshot"].endswith("_1_a.png")
    assert _pngs(env) == [err["screenshot"]]


def test_setup_crash_error_event_has_a_screenshot(env):
    def setup():
        raise ValueError("camera")
    with pytest.raises(ValueError):
        _run(env, {"a": lambda: "ok"}, setup=setup)
    err = next(e for e in _events(env) if e["event"] == "error")
    assert err["state"] == "starting" and err["screenshot"].endswith("_1_starting.png")


def test_force_stop_takes_no_screenshot(env):
    def stop():
        raise pause.ForceStop()
    assert _run(env, {"a": stop}) == "stopped"
    assert _pngs(env) == [] and not any("screenshot" in e for e in _events(env))


def test_keyboard_interrupt_takes_no_screenshot(env):
    def interrupt():
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        _run(env, {"a": interrupt})
    assert _pngs(env) == []


def test_no_shooter_outside_a_session(env):
    assert screenshots.current() is None
    assert screenshots.step_fields("a", "fail") == {}
    exc = RuntimeError("x")
    screenshots.tag_error(exc, "a")
    assert "screenshot" not in events.error_fields(exc)


# ── pieces ────────────────────────────────────────────────────────────────────

def test_file_name_is_safe_for_any_state():
    assert screenshots.file_name("/x/tanner/log/tanner_20261011_101500.jsonl", 3, "trade_ellis") == \
        "tanner_20261011_101500_3_trade_ellis.png"
    assert screenshots.file_name("bot_1.jsonl", 1, "../a b") == "bot_1_1____a_b.png"
    assert screenshots.file_name("bot_1.jsonl", 1, None) == "bot_1_1_None.png"


def test_config_marks_skips_missing_names_and_reads_lib_configs(monkeypatch):
    ge = types.SimpleNamespace(GE_REGION=(1, 2, 3, 4), BANK_CHECK=(5, 6, (0, 0, 0)))
    monkeypatch.setitem(screenshots.LIB_CONFIGS, "ge", lambda: ge)
    cfg = types.SimpleNamespace(ELLIS_REGION=(10, 20, 30, 40), BANK_CHECK=(7, 8, (1, 1, 1)))
    marks = screenshots.config_marks(
        {"trade_ellis": ["ELLIS_REGION", "NOT_IN_THIS_CONFIG"], "ge_bank": ["ge.GE_REGION", "ge.BANK_CHECK", "BANK_CHECK"]},
        cfg)
    assert marks("trade_ellis") == [("ELLIS_REGION", (10, 20, 30, 40))]
    assert marks("ge_bank") == [("ge.GE_REGION", (1, 2, 3, 4)), ("ge.BANK_CHECK", (5, 6, (0, 0, 0))),
                                ("BANK_CHECK", (7, 8, (1, 1, 1)))]
    assert marks("walk_to_bank") == []


def test_config_marks_lib_config_that_wont_import(monkeypatch):
    def missing():
        raise ImportError("no lib/ge_config.py")
    monkeypatch.setitem(screenshots.LIB_CONFIGS, "ge", missing)
    marks = screenshots.config_marks({"s": ["ge.GE_REGION", "A"]}, types.SimpleNamespace(A=(1, 1)))
    assert marks("s") == [("A", (1, 1))]


def test_error_fields_carry_a_tagged_screenshot():
    exc = RuntimeError("x")
    exc._runetools_screenshot = "bot_1_1_a.png"
    assert events.error_fields(exc)["screenshot"] == "bot_1_1_a.png"
    assert "screenshot" not in events.error_fields(RuntimeError("y"))


# ── a handler that waits before reporting its failure (review: miners) ────────

def test_failed_now_takes_the_shot_at_the_miss_not_after_the_wait(env, fake_screen):
    miss, later = canvas(400, 400, (200, 0, 0)), canvas(400, 400, (0, 200, 0))
    fake_screen.show(miss)

    def a():
        screenshots.failed_now("not_found")      # at the miss
        fake_screen.show(later)                  # the rock respawns during the retry wait
        return "not_found"
    calls = iter([a, lambda: "ok"])
    _run(env, {"a": lambda: next(calls)(), "b": lambda: "ok"})
    steps = [e for e in _events(env) if e["event"] == "step"]
    assert steps[0]["screenshot"].endswith("_1_a.png")
    assert _pngs(env) == [steps[0]["screenshot"]]                        # no second, late shot
    rgb = np.array(Image.open(env / steps[0]["screenshot"]).convert("RGB"))
    assert tuple(rgb[200, 200]) == (200, 0, 0)


def test_failed_now_then_ok_leaves_no_field(env):
    def a():
        screenshots.failed_now("fail")
        return "ok"
    _run(env, {"a": a, "b": lambda: "ok"})
    assert not any("screenshot" in e for e in _events(env) if e["event"] == "step")


def test_failed_now_outside_a_session_does_nothing():
    screenshots.finish()
    screenshots.failed_now("not_found")          # no shooter: no error


def test_error_screenshot_named_after_the_machine_state_not_stats_step(env):
    # varrock overwrites stats["step"] with a label ("magenta rock"); marks are keyed by state
    stats_holder = {}

    def a():
        stats_holder["stats"]["step"] = "magenta rock"
        raise RuntimeError("boom")
    marks = screenshots.config_marks({"a": ["R"]}, types.SimpleNamespace(R=(10, 60, 50, 30)))
    stats = {}
    stats_holder["stats"] = stats
    with pytest.raises(RuntimeError):
        run_session(stats, bot="demo", log_prefix=str(env / "bot"), intro=[], setup=lambda: None, session=_model,
                    handlers=lambda m: {"a": a}, final_states={"end"}, cycle_start=None,
                    summary=lambda m, f, l: "", marks=marks)
    err = next(e for e in _events(env) if e["event"] == "error")
    assert err["screenshot"].endswith("_1_a.png")
    rgb = np.array(Image.open(env / err["screenshot"]).convert("RGB"))
    assert tuple(rgb[60, 30]) == vision.MARK_COLORS[0]


def test_warning_comes_back_for_each_session(capsys, tmp_path, monkeypatch):
    def broken():
        raise OSError("no display")
    monkeypatch.setattr(screenshots, "grab_screen", broken)
    for _ in range(2):
        screenshots.start(str(tmp_path / "bot_1.jsonl"))
        screenshots.take("a")
    screenshots.finish()
    assert capsys.readouterr().err.count("screenshot not saved") == 2
