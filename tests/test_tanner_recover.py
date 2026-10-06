"""tanner recover(): after the glory teleport and the double doors, walk into
TP_BANK_REGION, wait until stopped, then find the booth in TP_BOOTH_REGION."""
import pytest

DOORS = [(10, 10), (20, 10), (20, 20)]
WALK = (100, 200, 50, 20)
BOOTH = (300, 400, 60, 30)


@pytest.fixture
def recover_env(with_example_config, monkeypatch):
    with_example_config("lib", "energy", config="energy_config")   # tanner imports it
    actions = with_example_config("tanner", "actions")
    calls = []
    monkeypatch.setattr(actions, "DOUBLE_DOORS_REGION", DOORS)
    monkeypatch.setattr(actions, "TP_BANK_REGION", WALK)
    monkeypatch.setattr(actions._cfg, "TP_BOOTH_REGION", BOOTH)
    monkeypatch.setattr(actions.time, "sleep", lambda s: None)
    monkeypatch.setattr(actions.pyautogui, "press", lambda key: calls.append(("press", key)))
    monkeypatch.setattr(actions, "human_right_click", lambda x, y: (x, y))
    monkeypatch.setattr(actions, "menu_click", lambda x, y: calls.append(("menu",)))
    monkeypatch.setattr(actions, "orient_west", lambda: calls.append(("west",)))
    monkeypatch.setattr(actions, "_wait_stopped", lambda: calls.append(("stopped",)))
    monkeypatch.setattr(actions, "random_area_click", lambda r: calls.append(("area", r)))
    monkeypatch.setattr(actions, "human_click", lambda x, y: calls.append(("click", x, y)))
    monkeypatch.setattr(actions, "do_bank", lambda skip_restock_check=False: calls.append(("bank",)) or True)
    monkeypatch.setattr(actions.pause, "wait", lambda: False)
    return actions, calls


def test_walks_into_tp_bank_region_then_finds_booth_in_booth_region(recover_env, monkeypatch):
    actions, calls = recover_env
    searched = []

    def find_color(color, tol, outside_pad=0, region=None, whole_screen=False):
        searched.append(region)
        return (330, 415), None
    monkeypatch.setattr(actions, "find_color", find_color)

    assert actions.recover() is True
    after_west = calls[calls.index(("west",)) + 1:]
    assert after_west == [("area", DOORS), ("stopped",), ("area", WALK), ("stopped",),
                          ("click", 330, 415), ("stopped",), ("bank",)]
    assert searched == [BOOTH]


def test_booth_not_found_fails_after_retries(recover_env, monkeypatch):
    actions, calls = recover_env
    tries = []
    monkeypatch.setattr(actions, "find_color", lambda *a, **k: tries.append(k.get("whole_screen")) or (None, None))
    assert actions.recover() is False
    assert ("bank",) not in calls
    after_west = calls[calls.index(("west",)) + 1:]
    assert sum(1 for c in after_west if c[0] == "click") == 0     # never clicked a booth
    # only the last try looks beyond TP_BOOTH_REGION, over the whole screen
    assert tries == [False] * (actions.MAX_BOOTH_TRIES - 1) + [True]


def test_uncalibrated_booth_region_fails_before_searching(recover_env, monkeypatch):
    actions, calls = recover_env
    monkeypatch.setattr(actions._cfg, "TP_BOOTH_REGION", (0, 0, 0, 0))
    monkeypatch.setattr(actions, "find_color", lambda *a, **k: pytest.fail("searched an empty region"))
    assert actions.recover() is False
    assert calls == []   # fails before teleporting: no glory charge spent on a doomed recovery
