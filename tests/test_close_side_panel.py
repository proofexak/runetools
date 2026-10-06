"""Walk to tanner: close the side panel first, however many Escapes it takes
(Escape is the inventory key: another tab -> inventory -> closed)."""
import pytest


@pytest.fixture
def tanner(with_example_config, monkeypatch):
    with_example_config("lib", "energy", config="energy_config")   # tanner imports it
    actions = with_example_config("tanner", "actions")
    calls = []
    monkeypatch.setattr(actions.pyautogui, "press", lambda key: calls.append(("press", key)))
    monkeypatch.setattr(actions.time, "sleep", lambda s: None)
    monkeypatch.setattr(actions, "random_area_click", lambda area: calls.append(("walk",)))
    monkeypatch.setattr(actions, "human_move", lambda x, y: None)
    monkeypatch.setattr(actions, "_wait_stopped", lambda: None)

    def panel(*states):
        seq = iter(states)
        last = [states[-1]]

        def is_open():
            try:
                last[0] = next(seq)
            except StopIteration:
                pass
            return last[0]
        monkeypatch.setattr(actions, "inventory_open", is_open)
    return actions, calls, panel


@pytest.mark.parametrize("states,escapes", [
    ((False,), 0),                    # nothing open
    ((True, False), 1),               # the inventory: one Escape closes it
    ((True, True, False), 2),         # another tab: Escape opens the inventory, the second closes it
])
def test_walk_closes_the_panel_then_walks(tanner, states, escapes):
    actions, calls, panel = tanner
    panel(*states)
    assert actions.walk_to_tanner() is True
    assert calls == [("press", "escape")] * escapes + [("walk",)]


def test_a_panel_that_will_not_close_fails_the_walk_instead_of_clicking_into_it(tanner, capsys):
    actions, calls, panel = tanner
    panel(True)
    assert actions.walk_to_tanner() is False
    assert calls == [("press", "escape")] * actions.MAX_PANEL_CLOSES       # and no ("walk",)
    assert "won't close" in capsys.readouterr().out
