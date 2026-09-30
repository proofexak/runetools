"""
Characterisation tests: pin what today's screen-reading functions return for
synthetic screens (PRO-13). Frozen — the refactor must keep these passing
unchanged.
"""
from lib.inventory import get_slots
from lib.screen import find_color, find_nearest_color, pixel_matches, get_pixel_color
from tests.fakescreen import canvas, paint

MAGENTA = (255, 0, 255)


def test_find_color_rect_returns_centroid_and_count(fake_screen):
    fake_screen.show(paint(canvas(400, 400), 40, 20, 10, 10, MAGENTA))
    assert find_color(MAGENTA, 10, region=(30, 10, 50, 50)) == ((44.5, 24.5), 100)


def test_find_color_not_found(fake_screen):
    fake_screen.show(canvas(400, 400))
    assert find_color(MAGENTA, 10, region=(30, 10, 50, 50)) == (None, 0)


def test_find_color_polygon_excludes_outside(fake_screen):
    fake_screen.show(paint(canvas(400, 400), 40, 40, 20, 20, MAGENTA))
    triangle = [(0, 0), (100, 0), (0, 100)]
    point, count = find_color(MAGENTA, 10, region=triangle)
    assert 0 < count < 400                        # only the part inside the triangle
    x, y = point
    assert x + y < 100                            # and the point is inside it too
    outside = [(200, 200), (300, 200), (200, 300)]
    assert find_color(MAGENTA, 10, region=outside) == (None, 0)


def test_find_color_tolerance_boundary(fake_screen):
    fake_screen.show(paint(canvas(400, 400), 40, 20, 10, 10, (255, 0, 245)))
    assert find_color(MAGENTA, 10, region=(30, 10, 50, 50))[1] == 100
    fake_screen.show(paint(canvas(400, 400), 40, 20, 10, 10, (255, 0, 244)))
    assert find_color(MAGENTA, 10, region=(30, 10, 50, 50)) == (None, 0)


def test_find_nearest_color_picks_cluster_nearest_to_point(fake_screen):
    c = canvas(400, 400)
    paint(c, 50, 100, 10, 10, MAGENTA)
    paint(c, 250, 100, 10, 10, MAGENTA)
    fake_screen.show(c)
    point, count = find_nearest_color(MAGENTA, 10, region=(0, 0, 400, 400), near=(300, 104))
    assert point == (254.5, 104.5) and count == 200


def test_find_nearest_color_equidistant_takes_first_found(fake_screen):
    c = canvas(400, 400)
    paint(c, 50, 100, 10, 10, MAGENTA)
    paint(c, 250, 100, 10, 10, MAGENTA)
    fake_screen.show(c)
    point, _ = find_nearest_color(MAGENTA, 10, region=(0, 0, 400, 400), near=(154.5, 104.5))
    assert point == (54.5, 104.5)


def test_pixel_matches_and_get_pixel_color(fake_screen):
    fake_screen.show(paint(canvas(400, 400), 10, 10, 1, 1, (100, 50, 30)))
    assert get_pixel_color(10, 10) == (100, 50, 30)
    assert pixel_matches(10, 10, (115, 50, 30)) is True
    assert pixel_matches(10, 10, (116, 50, 30)) is False


# ── Golden Nuggets ────────────────────────────────────────────────────────────

ANCHORS = [(100, 100), (220, 100), (100, 136)]   # 40px columns, 36px rows
BG = (10, 10, 10)


def _gn(with_example_config, monkeypatch):
    actions = with_example_config("miner.golden_nuggets", "actions")
    monkeypatch.setattr(actions.config, "INV_ANCHORS", ANCHORS)
    monkeypatch.setattr(actions.config, "SLOT_BG_COLOR", (0, 0, BG))
    monkeypatch.setattr(actions.config, "SLOT_BG_TOL", 20)
    return actions


def test_count_filled_slots_skips_slot_zero(fake_screen, with_example_config, monkeypatch):
    actions = _gn(with_example_config, monkeypatch)
    c = canvas(400, 400, BG)
    slots = get_slots(ANCHORS)
    for i in (0, 1, 2, 5, 10, 27):
        x, y = slots[i]
        paint(c, x - 3, y - 3, 6, 6, (200, 200, 200))
    fake_screen.show(c)
    assert actions.count_filled_slots() == 5


def test_count_filled_slots_needs_enough_deviating_pixels(fake_screen, with_example_config, monkeypatch):
    actions = _gn(with_example_config, monkeypatch)
    c = canvas(400, 400, BG)
    x, y = get_slots(ANCHORS)[3]
    paint(c, x, y, 2, 2, (200, 200, 200))          # 4 pixels: below the 5-pixel minimum
    fake_screen.show(c)
    assert actions.count_filled_slots() == 0


def test_count_broken_struts_counts_clusters_60px_apart(fake_screen, with_example_config, monkeypatch):
    actions = _gn(with_example_config, monkeypatch)
    c = canvas(400, 400)
    for x in (20, 120, 220):
        paint(c, x, 50, 5, 5, actions.config.STRUT_COLOR)
    paint(c, 240, 50, 5, 5, actions.config.STRUT_COLOR)   # 20px from the third: same strut
    fake_screen.show(c)
    assert actions.count_broken_struts((0, 0, 400, 200)) == 3
    fake_screen.show(canvas(400, 400))
    assert actions.count_broken_struts((0, 0, 400, 200)) == 0


def test_character_in_any_vein_bbox_containment(fake_screen, with_example_config, monkeypatch):
    actions = _gn(with_example_config, monkeypatch)
    monkeypatch.setattr(actions.config, "PAY_DIRT_REGION", (0, 0, 300, 300))
    fake_screen.show(paint(canvas(400, 400), 130, 130, 40, 40, actions.config.MAGENTA))
    monkeypatch.setattr(actions.config, "CHARACTER", (150, 150))
    assert actions.character_in_any_vein() is True
    monkeypatch.setattr(actions.config, "CHARACTER", (250, 250))
    assert actions.character_in_any_vein() is False
    fake_screen.show(canvas(400, 400))
    monkeypatch.setattr(actions.config, "CHARACTER", (150, 150))
    assert actions.character_in_any_vein() is False
