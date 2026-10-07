"""
Characterisation tests (PRO-13): pin today's results of the screen-driven
decisions in lib/mouse, lib/movement, lib/digit_templates, lib/ge and
lib/energy. Frozen — the refactor must keep these passing unchanged.
"""
import random

import numpy as np
import pytest
from PIL import Image

import lib.mouse as mouse
import lib.movement as movement
from lib.digit_templates import preprocess, segment_glyphs, read_number
from tests.fakescreen import canvas, paint

WHITE, BLACK = (255, 255, 255), (0, 0, 0)


class FakeTime:
    def __init__(self):
        self.t = 0.0

    def time(self):
        return self.t

    def sleep(self, s):
        self.t += s


# ── smart_right_click ─────────────────────────────────────────────────────────

@pytest.fixture
def right_click(fake_screen, monkeypatch):
    monkeypatch.setattr(mouse, "_move", lambda x, y: None)
    monkeypatch.setattr(mouse.time, "sleep", lambda s: None)
    monkeypatch.setattr(random, "randint", lambda a, b: 0)
    fake_screen.show(canvas(400, 400))
    return fake_screen


def test_smart_right_click_detects_menu_top_left(right_click, monkeypatch):
    menu = paint(canvas(400, 400), 120, 80, 40, 60, (93, 84, 71))
    monkeypatch.setattr(mouse.pyautogui, "rightClick", lambda: right_click.show(menu))
    ax, ay, mx, my = mouse.smart_right_click(150, 90, menu_scan_region=(100, 50, 200, 200))
    assert (ax, ay) == (150, 90)
    assert (mx, my) == (120, 80)


def test_smart_right_click_falls_back_to_click_coords(right_click, monkeypatch):
    monkeypatch.setattr(mouse.pyautogui, "rightClick", lambda: None)
    assert mouse.smart_right_click(150, 90, menu_scan_region=(100, 50, 200, 200)) == (150, 90, 150, 90)


# ── wait_until_stopped ────────────────────────────────────────────────────────

def test_wait_until_stopped_true_after_stable_frames(fake_screen, monkeypatch):
    monkeypatch.setattr(movement, "time", FakeTime())
    b, w = canvas(400, 400, BLACK), canvas(400, 400, WHITE)
    fake_screen.sequence([b, w, b, w, w, w, w])
    assert movement.wait_until_stopped((0, 0, 50, 50), paused_fn=None) is True
    assert fake_screen.grabs == 7


def test_wait_until_stopped_false_on_timeout(fake_screen, monkeypatch):
    monkeypatch.setattr(movement, "time", FakeTime())
    b, w = canvas(400, 400, BLACK), canvas(400, 400, WHITE)
    fake_screen.sequence([b, w] * 50)
    assert movement.wait_until_stopped((0, 0, 50, 50), timeout=2.0, paused_fn=None) is False


# ── read_number (energy digits) ───────────────────────────────────────────────

GLYPHS = {   # 3×5 bitmap glyphs, X = bright pixel
    "0": ["XXX", "X.X", "X.X", "X.X", "XXX"],
    "4": ["X.X", "X.X", "XXX", "..X", "..X"],
    "7": ["XXX", "..X", "..X", "..X", "..X"],
    "#": ["XXX", "XXX", "XXX", "XXX", "XXX"],   # not a digit
}


def _draw(c, text, x0, y0):
    for i, ch in enumerate(text):
        for dy, row in enumerate(GLYPHS[ch]):
            for dx, px in enumerate(row):
                if px == "X":
                    paint(c, x0 + i * 4 + dx, y0 + dy, 1, 1, WHITE)
    return c


def _templates():
    out = {}
    for digit in ("0", "4", "7"):
        img = Image.fromarray(_draw(canvas(20, 20), digit, 5, 5)[:, :, ::-1].copy())
        (glyph,) = segment_glyphs(preprocess(img))
        out[digit] = np.array(glyph)
    return out


def test_read_number_reads_synthetic_digits(fake_screen):
    fake_screen.show(_draw(canvas(400, 400), "47", 100, 100))
    assert read_number((100, 100, 7, 5), _templates()) == ("47", 47)


def test_read_number_unknown_glyph_is_question_mark(fake_screen):
    fake_screen.show(_draw(canvas(400, 400), "4#", 100, 100))
    raw, value = read_number((100, 100, 7, 5), _templates())
    assert raw == "4?" and value is None


# ── energy: when to drink ─────────────────────────────────────────────────────

@pytest.fixture
def energy(with_example_config, monkeypatch):
    energy = with_example_config("lib", "energy", config="energy_config")
    drinks = []
    monkeypatch.setattr(energy, "drink_stamina", lambda: drinks.append(1))
    return energy, drinks


@pytest.mark.parametrize("reading,drinks", [(29, 1), (30, 0), (None, 0)])
def test_maybe_drink_threshold(energy, monkeypatch, reading, drinks):
    energy, drunk = energy
    monkeypatch.setattr(energy, "read_energy", lambda: reading)
    assert energy.maybe_drink_stamina(threshold=30) is bool(drinks)
    assert len(drunk) == drinks


class _Proceeded(Exception):
    pass


def _explode(*a):
    raise _Proceeded()


def test_restock_unreadable_energy_proceeds(energy, monkeypatch):
    energy, _ = energy
    monkeypatch.setattr(energy, "read_energy", lambda: None)
    monkeypatch.setattr(energy, "human_click", _explode)
    with pytest.raises(_Proceeded):
        energy.restock_stamina_at_bank()


def test_restock_skips_when_energy_fine(energy, monkeypatch):
    energy, _ = energy
    monkeypatch.setattr(energy, "read_energy", lambda: energy.cfg.DRINK_THRESHOLD)
    monkeypatch.setattr(energy, "human_click", _explode)
    assert energy.restock_stamina_at_bank() is False


def test_restock_force_proceeds_even_when_fine(energy, monkeypatch):
    energy, _ = energy
    monkeypatch.setattr(energy, "read_energy", lambda: 100)
    monkeypatch.setattr(energy, "human_click", _explode)
    with pytest.raises(_Proceeded):
        energy.restock_stamina_at_bank(force=True)
