import pytest

import lib.pause as pause
from lib.state_machine import run_machine
from crafting.states import build_machine, FINAL_STATES, CYCLE_START

ITEMS = [{"click_point": (1, 1), "done_point": (2, 2)},
         {"click_point": (3, 3), "done_point": (4, 4), "skip": True},
         {"click_point": (5, 5), "done_point": (6, 6)}]


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(pause, "wait", lambda: None)


def drive(session, stop_after_items=None):
    crafted, steps = [], []

    def grab():
        return "ok"

    def craft():
        item = session.next_item()
        steps.append((session.stats["run"], session.stats["step"]))
        crafted.append(item["click_point"])
        session.item_done()
        if stop_after_items and len(crafted) == stop_after_items:
            session.stats["stop"] = True
        return "ok"
    final = run_machine(session, {"grab_currency": grab, "craft": craft}, session.stats,
                        FINAL_STATES, CYCLE_START)
    return final, crafted, steps


def test_crafts_non_skipped_items_then_done(capsys):
    s = build_machine({}, ITEMS)
    final, crafted, steps = drive(s)
    assert final == "done"
    assert crafted == [(1, 1), (5, 5)]
    assert steps == [(1, "item 1/2"), (2, "item 2/2")]
    assert "All items done." in capsys.readouterr().out


def test_no_items_goes_straight_to_done():
    s = build_machine({}, [{"click_point": (0, 0), "done_point": (0, 0), "skip": True}])
    final, crafted, _ = drive(s)
    assert final == "done" and crafted == []


def test_stop_before_next_item():
    s = build_machine({}, ITEMS)
    final, crafted, _ = drive(s, stop_after_items=1)
    assert final == "stopped" and crafted == [(1, 1)]


def test_starts_at_grab_currency():
    s = build_machine({}, ITEMS)
    assert s.state == "grab_currency" and s.total == 2 and s.index == 0
