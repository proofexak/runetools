"""Glory / ring of wealth teleports: one left-click on the worn item when RuneLite's
Menu Entry Swapper makes that the teleport (…_LEFT_CLICK_TP), else the right-click
menu as before — also for a calibrated config that doesn't have the line yet."""
import pytest

from tests.test_tanner_recover import BOOTH, DOORS, WALK, recover_env   # noqa: F401  (fixture)


@pytest.mark.parametrize("left_click", [True, False])
def test_glory_recovery_teleport(recover_env, monkeypatch, left_click):
    actions, calls = recover_env
    monkeypatch.setattr(actions._cfg, "AMULET_LEFT_CLICK_TP", left_click)
    monkeypatch.setattr(actions, "AMULET_SLOT", (1465, 623))
    monkeypatch.setattr(actions, "find_color", lambda *a, **k: ((330, 415), 50))
    assert actions.recover() is True
    before_west = calls[:calls.index(("west",))]
    clicks = [c for c in before_west if c[0] == "click"]
    if left_click:
        assert ("menu",) not in before_west
        assert len(clicks) == 1 and abs(clicks[0][1] - 1465) <= 3 and abs(clicks[0][2] - 623) <= 3
    else:
        assert ("menu",) in before_west and clicks == []


def test_glory_config_without_the_line_keeps_the_right_click_menu(recover_env, monkeypatch):
    actions, calls = recover_env
    monkeypatch.delattr(actions._cfg, "AMULET_LEFT_CLICK_TP", raising=False)
    monkeypatch.setattr(actions, "find_color", lambda *a, **k: ((330, 415), 50))
    assert actions.recover() is True
    assert ("menu",) in calls[:calls.index(("west",))]


@pytest.fixture
def ge(with_example_config, monkeypatch):
    ge = with_example_config("lib", "ge", config="ge_config")
    calls = []
    monkeypatch.setattr(ge.pyautogui, "press", lambda key: None)
    monkeypatch.setattr(ge.time, "sleep", lambda s: None)
    monkeypatch.setattr(ge, "human_click", lambda x, y: calls.append(("click", x, y)))
    monkeypatch.setattr(ge, "smart_right_click", lambda *a, **k: calls.append(("right",)) or (0, 0, 10, 10))
    monkeypatch.setattr(ge, "menu_click", lambda x, y: calls.append(("menu",)))
    monkeypatch.setattr(ge.cfg, "RING_SLOT", (1843, 916))
    return ge, calls


@pytest.mark.parametrize("left_click", [True, False])
def test_ring_of_wealth_teleport_to_the_ge(ge, monkeypatch, left_click):
    ge, calls = ge
    monkeypatch.setattr(ge.cfg, "RING_LEFT_CLICK_TP", left_click)
    ge._teleport()
    if left_click:
        assert len(calls) == 1 and calls[0][0] == "click"
        assert abs(calls[0][1] - 1843) <= 3 and abs(calls[0][2] - 916) <= 3
    else:
        assert calls == [("right",), ("menu",)]


def test_ring_config_without_the_line_keeps_the_right_click_menu(ge, monkeypatch):
    ge, calls = ge
    monkeypatch.delattr(ge.cfg, "RING_LEFT_CLICK_TP", raising=False)
    ge._teleport()
    assert calls == [("right",), ("menu",)]
