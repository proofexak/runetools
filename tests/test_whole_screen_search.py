"""Whole-screen last try: a click target not in its calibrated region is looked
for once over the whole screen (nearest cluster to the region), never inside
the bot's own overlay."""
import numpy as np
import pytest

import lib.screen as screen
import lib.vision as vision
from tests.fakescreen import canvas, paint

BLUE = (0, 0, 255)
REGION = (100, 100, 50, 50)          # centre (125, 125)


@pytest.fixture(autouse=True)
def _no_exclusions(monkeypatch):
    monkeypatch.setattr(screen, "_excluded", {})


# ── pure helpers ──────────────────────────────────────────────────────────────

def test_region_center_of_rect_and_polygon():
    assert vision.region_center((100, 100, 50, 20)) == (125, 110)
    assert vision.region_center([(0, 0), (40, 10), (20, 30)]) == (20, 15)


def test_blank_rects_paints_black_in_frame_coords_and_clips():
    frame = np.full((10, 10, 3), 200, dtype=np.uint8)
    out = vision.blank_rects(frame, [(102, 103, 3, 2), (108, 108, 50, 50)], origin=(100, 100))
    assert out[3:5, 2:5].max() == 0 and out[8:, 8:].max() == 0      # second rect clipped to the frame
    assert out[0, 0].tolist() == [200, 200, 200] and frame.min() == 200   # input untouched
    assert vision.blank_rects(frame, [(500, 500, 5, 5)], origin=(0, 0)).min() == 200


# ── against a fake screen ─────────────────────────────────────────────────────

def test_without_the_flag_a_target_outside_the_region_is_not_found(fake_screen):
    fake_screen.show(paint(canvas(400, 400), 300, 300, 6, 6, BLUE))
    assert screen.find_color(BLUE, 10, region=REGION) == (None, 0)


def test_last_try_finds_it_on_the_whole_screen_nearest_the_region(fake_screen, capsys):
    c = canvas(400, 400)
    paint(c, 350, 350, 6, 6, BLUE)                  # far from the region
    paint(c, 170, 130, 6, 6, BLUE)                  # just outside it: this one
    fake_screen.show(c)
    (x, y), count = screen.find_color(BLUE, 10, region=REGION, jitter_pct=0, whole_screen=True)
    assert (round(x), round(y)) == (172, 132) and count == 72
    assert "found on the whole screen" in capsys.readouterr().out


def test_in_the_region_the_whole_screen_is_not_searched(fake_screen):
    c = canvas(400, 400)
    paint(c, 110, 110, 4, 4, BLUE)
    fake_screen.show(c)
    grabs = fake_screen.grabs
    (x, y), _ = screen.find_color(BLUE, 10, region=REGION, jitter_pct=0, whole_screen=True)
    assert (x, y) == (111.5, 111.5) and fake_screen.grabs == grabs + 1


def test_polygon_region_falls_back_too(fake_screen):
    fake_screen.show(paint(canvas(400, 400), 20, 300, 4, 4, BLUE))
    pos, _ = screen.find_color(BLUE, 10, region=[(100, 100), (150, 100), (125, 150)], whole_screen=True)
    assert pos is not None


def test_the_overlay_is_never_matched(fake_screen, capsys):
    fake_screen.show(paint(canvas(400, 400), 300, 10, 20, 20, BLUE))   # only match: inside the overlay
    screen.exclude("overlay", (290, 0, 110, 60))
    assert screen.find_color(BLUE, 10, region=REGION, whole_screen=True) == (None, 0)
    assert "not on the whole screen either" in capsys.readouterr().out
    screen.exclude("overlay", None)
    assert screen.find_color(BLUE, 10, region=REGION, whole_screen=True)[0] is not None


def test_find_nearest_color_falls_back_nearest_its_point(fake_screen):
    c = canvas(400, 400)
    paint(c, 20, 20, 4, 4, BLUE)
    paint(c, 380, 380, 4, 4, BLUE)
    fake_screen.show(c)
    (x, y), _ = screen.find_nearest_color(BLUE, 10, region=REGION, near=(390, 390), jitter_pct=0,
                                          whole_screen=True)
    assert (round(x), round(y)) == (382, 382)
    assert screen.find_nearest_color(BLUE, 10, region=REGION, near=(390, 390)) == (None, 0)


# ── bots ask for it on their final attempt only ───────────────────────────────

@pytest.fixture
def tanner_actions(with_example_config, monkeypatch):
    with_example_config("lib", "energy", config="energy_config")   # tanner imports it
    actions = with_example_config("tanner", "actions")
    monkeypatch.setattr(actions.time, "sleep", lambda s: None)
    monkeypatch.setattr(actions.pause, "wait", lambda: False)
    return actions


def test_tanner_ellis_searches_the_whole_screen_on_the_very_last_attempt(tanner_actions, monkeypatch):
    actions = tanner_actions
    monkeypatch.setattr(actions, "MAX_ELLIS_ROUNDS", 2)
    monkeypatch.setattr(actions, "MAX_ELLIS_TRIES", 3)
    tries = []
    monkeypatch.setattr(actions, "find_color", lambda *a, **k: tries.append(k["whole_screen"]) or (None, 0))
    assert actions.trade_ellis() is False
    assert tries == [False] * 5 + [True]


def test_tanner_bank_booth_searches_the_whole_screen_on_the_last_attempt(tanner_actions, monkeypatch):
    actions = tanner_actions
    tries = []
    monkeypatch.setattr(actions, "find_color", lambda *a, **k: tries.append(k["whole_screen"]) or (None, 0))
    assert actions.click_bank_booth() is False
    assert tries == [False] * (actions.MAX_BOOTH_TRIES - 1) + [True]
