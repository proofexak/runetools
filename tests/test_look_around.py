"""Look around before the glory: one whole-screen look for several colours
(lib.screen.look_for) and the tanner's decision on what it sees."""
import pytest

import lib.screen as screen
import lib.vision as vision
from tests.fakescreen import canvas, paint

BLUE, MAGENTA = (0, 0, 255), (255, 0, 255)


# ── lib: one look for several colours ─────────────────────────────────────────

def test_find_targets_nearest_cluster_per_colour_or_none():
    c = canvas(200, 200)
    paint(c, 10, 10, 4, 4, BLUE)
    paint(c, 150, 150, 4, 4, BLUE)
    paint(c, 100, 20, 4, 4, MAGENTA)
    seen = vision.find_targets(c, {"near_blue": (BLUE, 10, (160, 160)), "purple": (MAGENTA, 10, (0, 0)),
                                   "green": ((0, 255, 0), 10, (0, 0))}, jitter_pct=0)
    assert seen == {"near_blue": (151.5, 151.5), "purple": (101.5, 21.5), "green": None}


def test_look_for_uses_screen_coords_and_skips_the_overlay(fake_screen, monkeypatch):
    monkeypatch.setattr(screen, "_excluded", {})
    fake_screen.monitor = (0, 0)
    c = canvas(400, 400)
    paint(c, 300, 10, 20, 20, BLUE)          # inside the overlay
    paint(c, 50, 300, 6, 6, MAGENTA)
    fake_screen.show(c)
    screen.exclude("overlay", (290, 0, 110, 60))
    seen = screen.look_for({"ellis": (BLUE, 10, (200, 200)), "booth": (MAGENTA, 10, (200, 200))}, jitter_pct=0)
    assert seen == {"ellis": None, "booth": (52.5, 302.5)}
    assert fake_screen.grabs == 1            # one look for both colours


# ── tanner: what it does with what it sees ────────────────────────────────────

@pytest.fixture
def tanner(with_example_config, monkeypatch):
    with_example_config("lib", "energy", config="energy_config")   # tanner imports it
    actions = with_example_config("tanner", "actions")
    calls = []
    monkeypatch.setattr(actions, "human_click", lambda x, y: calls.append(("click", x, y)))
    monkeypatch.setattr(actions, "_wait_stopped", lambda: calls.append(("stopped",)))
    monkeypatch.setattr(actions, "click_tan_all", lambda: calls.append(("tan",)) or True)

    def sees(ellis=None, booth=None):
        monkeypatch.setattr(actions, "look_for", lambda targets: {"ellis": ellis, "booth": booth})
    return actions, calls, sees


def test_needs_ellis_and_sees_him_tans(tanner):
    actions, calls, sees = tanner
    sees(ellis=(700, 400), booth=(300, 300))
    assert actions.look_around("ellis") == "tanned"
    assert calls == [("click", 700, 400), ("stopped",), ("tan",)]


def test_needs_ellis_sees_only_the_booth_banks_to_get_back_on_track(tanner):
    actions, calls, sees = tanner
    sees(booth=(300, 300))
    assert actions.look_around("ellis") == "bank"
    assert calls == [("click", 300, 300), ("stopped",)]


def test_ellis_who_does_not_open_the_tanning_window_is_lost(tanner, monkeypatch):
    actions, calls, sees = tanner
    sees(ellis=(700, 400), booth=(300, 300))
    monkeypatch.setattr(actions, "click_tan_all", lambda: False)
    assert actions.look_around("ellis") == "lost"


def test_needs_the_bank_goes_to_the_booth_even_if_ellis_is_closer(tanner):
    actions, calls, sees = tanner
    sees(ellis=(980, 520), booth=(300, 300))
    assert actions.look_around("bank") == "bank"
    assert calls == [("click", 300, 300), ("stopped",)]


@pytest.mark.parametrize("need,seen", [
    ("bank", {"ellis": (700, 400)}),          # carrying leather: Ellis is no help
    ("bank", {}),
    ("ellis", {}),
])
def test_nothing_useful_in_sight_is_lost(tanner, need, seen, capsys):
    actions, calls, sees = tanner
    sees(**seen)
    assert actions.look_around(need) == "lost"
    assert calls == []
    assert "glory recovery" in capsys.readouterr().out
