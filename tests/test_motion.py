import math
import random
import statistics

import lib.motion as motion
from lib.human import DEFAULT


def resample_50ms(pts):
    """What the server sees: the cursor position at t = 0, 0.05, 0.10, … (last position held)."""
    out, i, t = [], 0, 0.0
    while t <= pts[-1][0] + 1e-9:
        while i + 1 < len(pts) and pts[i + 1][0] <= t:
            i += 1
        out.append(pts[i][1:])
        t += 0.05
    if out[-1] != pts[-1][1:]:
        out.append(pts[-1][1:])
    return out


def count_local_maxima(xs, floor):
    return sum(1 for i, v in enumerate(xs)
               if v >= floor and (i == 0 or v > xs[i - 1]) and (i == len(xs) - 1 or v >= xs[i + 1]))


def test_plan_move_zero_distance():
    assert motion.plan_move((100, 100), (100, 101), 16, DEFAULT, random.Random(0)) == [(0.0, 100, 101)]


def test_plan_ends_exactly_on_target_with_increasing_time():
    pts = motion.plan_move((50, 60), (450, 300), 16, DEFAULT, random.Random(1))
    assert pts[-1][1:] == (450, 300)
    assert all(b[0] > a[0] for a, b in zip(pts, pts[1:]))


def test_plan_move_never_touches_corner():
    for s in range(300):
        pts = motion.plan_move((500, 500), (2, 2), 16, DEFAULT, random.Random(s))
        assert min(min(x, y) for _, x, y in pts) >= 1


def test_duration_follows_fitts():
    mt = motion.fitts_time(400, 30, DEFAULT)
    for s in range(100):
        pts = motion.plan_move((10, 10), (410, 10), 30, DEFAULT, random.Random(s))
        assert mt - 1e-6 <= pts[-1][0] <= mt + 0.1


def test_sample_intervals_vary():
    pts = motion.plan_move((10, 10), (410, 210), 16, DEFAULT, random.Random(2))
    dts = [b[0] - a[0] for a, b in zip(pts, pts[1:])]
    steps = [d for d in dts if d <= 0.0101]
    gaps = [d for d in dts if d > 0.0101]           # the pause before a correction
    assert statistics.pstdev(steps) > 0.0005
    assert len(gaps) <= 1 and all(0.03 <= g <= 0.0901 for g in gaps)


def test_reciprocal_is_fast_and_single():
    pts = motion.plan_move((100, 100), (100, 140), 30, DEFAULT, random.Random(3), mode="reciprocal")
    assert pts[-1][0] < 0.25


def test_click_offset_gaussian_and_clamped():
    rng = random.Random(4)
    xs = [motion.click_offset(16, DEFAULT, rng) for _ in range(20000)]
    assert max(map(abs, xs)) <= 8
    assert 0.8 * 0.23 * 16 < statistics.pstdev(xs) < 1.1 * 0.23 * 16
    assert xs.count(0) > xs.count(7)          # peaked, not uniform


def test_dwell_modes():
    rng = random.Random(5)
    aim = [motion.dwell(DEFAULT, rng) for _ in range(2000)]
    rec = [motion.dwell(DEFAULT, rng, mode="reciprocal") for _ in range(2000)]
    assert 0.18 <= statistics.median(aim) <= 0.28 and min(aim) > 0
    assert all(0.04 <= d <= 0.09 for d in rec)


def test_human_likeness_at_50ms():
    peaks, devs, subs = [], [], []
    for s in range(200):
        pts = motion.plan_move((100, 300), (500, 300), 16, DEFAULT, random.Random(s))
        xy = resample_50ms(pts)
        speed = [math.dist(a, b) for a, b in zip(xy, xy[1:])]
        peaks.append(speed.index(max(speed)) / len(speed))
        devs.append(max(abs(y - 300) for _, y in xy) / 400)
        subs.append(count_local_maxima(speed, floor=0.1 * max(speed)))
    assert 0.15 <= statistics.median(peaks) <= 0.45
    assert 0.01 <= statistics.median(devs) <= 0.08
    assert sum(1 <= n <= 3 for n in subs) >= 0.9 * len(subs)


def test_plan_move_never_touches_bottom_right_corner():
    for s in range(300):
        pts = motion.plan_move((960, 540), (1905, 1065), 16, DEFAULT, random.Random(s), bounds=(1920, 1080))
        assert max(x for _, x, _ in pts) <= 1918 and max(y for _, _, y in pts) <= 1078
