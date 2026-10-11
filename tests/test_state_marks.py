"""Each bot's STATE_MARKS (PRO-91): the config regions / points drawn on a failing state's
screenshot must name real states and fields the bot's config template has."""
import importlib
import importlib.util
import os

import pytest

import lib.screenshots as screenshots
import lib.vision as vision

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BOTS = ["tanner", "choc", "miner.golden_nuggets", "miner.varrock_exp"]


def _example(*parts):
    path = os.path.join(ROOT, *parts)
    spec = importlib.util.spec_from_file_location("_example_" + "_".join(parts), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LIB = {"ge": _example("lib", "ge_config.example.py"), "energy": _example("lib", "energy_config.example.py")}


@pytest.mark.parametrize("bot", BOTS)
def test_state_marks_name_real_states_and_config_fields(bot):
    states = importlib.import_module(f"{bot}.states")
    config = _example(*bot.split("."), "config.example.py")
    assert states.STATE_MARKS, bot
    for state, names in states.STATE_MARKS.items():
        assert state in states.STATES, (bot, state)
        assert state not in states.FINAL_STATES, (bot, state)
        for name in names:
            prefix, dot, attr = name.partition(".")
            source, field = (LIB[prefix], attr) if dot else (config, name)
            assert hasattr(source, field), (bot, state, name)
            # a region, a point or a polygon — something draw_marks can place once calibrated
            value = getattr(source, field)
            calibrated = value
            if isinstance(value, tuple) and len(value) == 4:
                calibrated = (1, 1, 1, 1)
            elif isinstance(value, tuple) and len(value) in (2, 3):
                calibrated = (1, 1) + tuple(value[2:])
            elif isinstance(value, list):
                calibrated = [(1, 1), (5, 1), (5, 5)]
            assert vision.mark_shape(calibrated) is not None, (bot, state, name, value)


def test_tanner_trade_ellis_draws_ellis_region(monkeypatch):
    import types
    from tanner.states import STATE_MARKS
    monkeypatch.setitem(screenshots.LIB_CONFIGS, "ge", lambda: LIB["ge"])
    cfg = types.SimpleNamespace(ELLIS_REGION=(10, 20, 30, 40), TANNING_CHECK=(5, 6, (1, 2, 3)))
    assert screenshots.config_marks(STATE_MARKS, cfg)("trade_ellis") == [
        ("ELLIS_REGION", (10, 20, 30, 40)), ("TANNING_CHECK", (5, 6, (1, 2, 3)))]
