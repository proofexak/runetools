"""Unit tests for the non-vision pure logic split out in PRO-13."""
import numpy as np
import pytest
from PIL import Image

from lib.movement import Stillness
from lib.digit_templates import parse_number, preprocess, segment_glyphs
from choc.logic import restock_due
from tests.fakescreen import canvas, paint


def test_stillness_needs_consecutive_calm_frames():
    s = Stillness(thresh=3.0, stable_count=3)
    assert [s.update(d) for d in (5.0, 1.0, 1.0)] == [False, False, False]
    assert s.update(3.0) is True               # diff == thresh counts as calm


def test_stillness_resets_on_motion():
    s = Stillness(thresh=3.0, stable_count=3)
    assert [s.update(d) for d in (1.0, 1.0, 9.0, 1.0, 1.0)] == [False] * 5
    assert s.update(1.0) is True


def _glyph_image(rows):
    c = canvas(20, 20)
    for dy, row in enumerate(rows):
        for dx, px in enumerate(row):
            if px == "X":
                paint(c, 5 + dx, 5 + dy, 1, 1, (255, 255, 255))
    return Image.fromarray(c[:, :, ::-1].copy())


SEVEN = ["XXX", "..X", "..X", "..X", "..X"]
ZERO = ["XXX", "X.X", "X.X", "X.X", "XXX"]


def test_parse_number_reads_image():
    templates = {d: np.array(segment_glyphs(preprocess(_glyph_image(g)))[0])
                 for d, g in (("7", SEVEN), ("0", ZERO))}
    both = [a + "." + b for a, b in zip(SEVEN, ZERO)]
    assert parse_number(_glyph_image(both), templates) == ("70", 70)
    assert parse_number(_glyph_image(both), {}) == ("??", None)
    assert parse_number(canvas_image(), templates) == ("", None)


def canvas_image():
    return Image.fromarray(canvas(20, 20))


@pytest.fixture
def needs_stamina(with_example_config):
    return with_example_config("lib", "energy", config="energy_config").needs_stamina


@pytest.mark.parametrize("energy,force,if_unreadable,expected", [
    (29, False, False, True),
    (30, False, False, False),
    (100, True, False, True),
    (None, False, False, False),
    (None, False, True, True),
    (None, True, False, True),
])
def test_needs_stamina(needs_stamina, energy, force, if_unreadable, expected):
    assert needs_stamina(energy, 30, force=force, if_unreadable=if_unreadable) is expected


@pytest.mark.parametrize("remaining,grind,expected", [(40, 20, False), (39, 20, True), (20, 20, True)])
def test_restock_due(remaining, grind, expected):
    assert restock_due(remaining, grind) is expected
