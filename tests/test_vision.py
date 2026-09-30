"""Unit tests for lib/vision.py — pure functions over synthetic frames."""
import numpy as np
import pytest

from lib import vision
from tests.fakescreen import canvas, paint

MAGENTA = (255, 0, 255)


class Rng:
    """triangular() returns the mode, the low end or the high end."""
    def __init__(self, pick="mode"):
        self.pick = pick

    def triangular(self, low, high, mode):
        return {"mode": mode, "low": low, "high": high}[self.pick]


# ── masks & colour ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("channel", [0, 1, 2])
def test_color_mask_tolerance_boundary_per_channel(channel):
    for delta, expected in ((10, True), (11, False)):
        rgb = list(MAGENTA)
        rgb[channel] = rgb[channel] - delta if rgb[channel] else delta
        frame = paint(canvas(5, 5), 2, 2, 1, 1, tuple(rgb))
        assert bool(vision.color_mask(frame, MAGENTA, 10)[2, 2]) is expected


def test_color_mask_reads_bgr_frames_as_rgb():
    frame = canvas(4, 4, (255, 0, 0))                 # pure red, stored BGR
    assert vision.color_mask(frame, (255, 0, 0), 0).all()
    assert not vision.color_mask(frame, (0, 0, 255), 0).any()


def test_polygon_mask_square():
    mask = vision.polygon_mask(10, 10, [(2, 2), (6, 2), (6, 6), (2, 6)])
    assert mask.shape == (10, 10)
    assert mask[4, 4] and not mask[0, 0] and not mask[8, 8]


def test_color_close_boundary():
    assert vision.color_close((100, 50, 30), (115, 35, 45), 15) is True
    assert vision.color_close((100, 50, 30), (116, 50, 30), 15) is False


# ── click point & locate ──────────────────────────────────────────────────────

def test_click_point_is_centroid_at_mode():
    xs, ys = np.array([0, 10]), np.array([0, 20])
    assert vision.click_point(xs, ys, 0.25, rng=Rng()) == (5.0, 10.0)


def test_click_point_spread_is_jitter_pct_of_bbox():
    xs, ys = np.array([0, 10]), np.array([0, 20])
    assert vision.click_point(xs, ys, 0.25, rng=Rng("low")) == (2.5, 5.0)
    assert vision.click_point(xs, ys, 0.25, rng=Rng("high")) == (7.5, 15.0)


def test_locate_centroid_and_count():
    frame = paint(canvas(50, 50), 10, 10, 10, 10, MAGENTA)
    assert vision.locate(frame, MAGENTA, 10, rng=Rng()) == ((14.5, 14.5), 100)


def test_locate_empty_frame():
    assert vision.locate(canvas(50, 50), MAGENTA, 10, rng=Rng()) == (None, 0)


def test_locate_polygon_limits_matches():
    frame = paint(canvas(50, 50), 0, 0, 50, 50, MAGENTA)
    square = [(10, 10), (19, 10), (19, 19), (10, 19)]
    point, count = vision.locate(frame, MAGENTA, 10, polygon=square, rng=Rng())
    assert count == int(vision.polygon_mask(50, 50, square).sum())
    assert 10 <= point[0] <= 19 and 10 <= point[1] <= 19


# ── clusters ──────────────────────────────────────────────────────────────────

def _points(frame, rgb=MAGENTA, tol=10):
    ys, xs = np.where(vision.color_mask(frame, rgb, tol))
    return xs.astype(float), ys.astype(float)


def test_clusters_separate_blobs():
    frame = paint(paint(canvas(200, 50), 10, 10, 5, 5, MAGENTA), 150, 10, 5, 5, MAGENTA)
    groups = vision.clusters(*_points(frame), radius=30)
    assert [int(g.sum()) for g in groups] == [25, 25]


def test_clusters_seed_rule_splits_a_long_bar():
    # members are within `radius` of the seed (first remaining point), not of each other
    frame = paint(canvas(200, 10), 0, 5, 100, 1, MAGENTA)
    groups = vision.clusters(*_points(frame), radius=60)
    assert [int(g.sum()) for g in groups] == [61, 39]


def test_clusters_empty():
    assert vision.clusters(np.array([]), np.array([]), radius=30) == []


def test_nearest_cluster_point_picks_nearer():
    frame = paint(paint(canvas(400, 200), 50, 100, 10, 10, MAGENTA), 250, 100, 10, 10, MAGENTA)
    point, count = vision.nearest_cluster_point(frame, MAGENTA, 10, near=(300, 104), rng=Rng())
    assert point == (254.5, 104.5) and count == 200


def test_nearest_cluster_point_equidistant_takes_first():
    frame = paint(paint(canvas(400, 200), 50, 100, 10, 10, MAGENTA), 250, 100, 10, 10, MAGENTA)
    point, _ = vision.nearest_cluster_point(frame, MAGENTA, 10, near=(154.5, 104.5), rng=Rng())
    assert point == (54.5, 104.5)


def test_nearest_cluster_point_empty():
    assert vision.nearest_cluster_point(canvas(50, 50), MAGENTA, 10, near=(0, 0)) == (None, 0)


def test_count_clusters():
    frame = canvas(400, 100)
    for x in (20, 120, 220, 240):
        paint(frame, x, 50, 5, 5, MAGENTA)
    assert vision.count_clusters(frame, MAGENTA, 10, radius=60) == 3
    assert vision.count_clusters(canvas(10, 10), MAGENTA, 10, radius=60) == 0


def test_point_in_any_cluster():
    frame = paint(canvas(300, 300), 130, 130, 40, 40, MAGENTA)
    assert vision.point_in_any_cluster(frame, MAGENTA, 10, (150, 150), radius=40) is True
    assert vision.point_in_any_cluster(frame, MAGENTA, 10, (250, 250), radius=40) is False
    assert vision.point_in_any_cluster(canvas(300, 300), MAGENTA, 10, (150, 150), radius=40) is False
