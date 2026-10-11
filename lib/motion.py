"""
Human mouse movement as data — PRO-8. Pure: no pyautogui, no sleeping.

plan_move() returns where the cursor should be when: [(t seconds from 0, x, y), ...].
lib/mouse.py plays it on a clock. The shape follows measured human pointing:

- duration from Fitts's law (MacKenzie 1991), per-account a and b
- speed peaks early, ~30% into the move, and decelerates for the rest (Phillips & Triggs)
- the first movement usually lands a little short (Müller 2017) or long (Phillips &
  Triggs), then one short correction after a ~30-90 ms pause (Chapuis 2007)
- a sideways bow of a few % of the distance (MacKenzie 2001), bending the way this
  player bends, sometimes crossing the straight line
- points every 6-10 ms, irregular, never in a screen corner (pyautogui's failsafe):
  x, y >= 1 and, given the screen size, <= size - 2

click_offset(): Gaussian scatter around the target centre, SD ≈ width / 4.1 (ISO 9241-9).
dwell(): the pause between arriving on a target and clicking it.
"""
import math
import random

STEP = (0.006, 0.010)          # s between points
PAUSE = (0.03, 0.09)           # s between the first movement and the correction
CORRECTION_PEAK = 0.4
RECIPROCAL_SPEEDUP = 0.6       # back and forth between two close targets: one fluid movement


def fitts_time(distance, width, profile):
    return profile.fitts_a + profile.fitts_b * math.log2(distance / width + 1)


def click_offset(width, profile, rng=random):
    """One axis' offset from the target centre, in px, kept on the target."""
    half = int(width // 2)
    return max(-half, min(half, round(rng.gauss(0, profile.click_sd_frac * width))))


def dwell(profile, rng=random, mode="aim"):
    """Seconds between the cursor stopping on a target and the click."""
    if mode == "reciprocal":
        return rng.uniform(0.04, 0.09)
    return rng.lognormvariate(math.log(profile.dwell_median), 0.3)


def _warp(tau, peak):
    """Fraction of the path done at normalised time tau: the Beta(2, 1/peak) CDF,
    whose density (the speed) peaks at tau = peak."""
    b = 1 / peak
    return 1 - (1 - tau) ** b * (1 + b * tau)


def _bezier(u, p0, p1, p2, p3):
    v = 1 - u
    return tuple(v**3 * a + 3 * v**2 * u * b + 3 * v * u**2 * c + u**3 * d
                 for a, b, c, d in zip(p0, p1, p2, p3))


def _segment(p0, p1, p2, p3, duration, peak, t0, rng, first=True):
    """Points along one Bézier, time-warped, from t0 to t0 + duration."""
    out, t = [], 0.0
    if not first:
        t = rng.uniform(*STEP)
    while t < duration:
        out.append((t0 + t, _bezier(_warp(t / duration, peak), p0, p1, p2, p3)))
        t += rng.uniform(*STEP)
    out.append((t0 + duration, p3))
    return out


def _along(a, b, f, side=0.0):
    """The point a fraction f along a→b, pushed `side` px to its left."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy) or 1.0
    return (a[0] + dx * f - dy / d * side, a[1] + dy * f + dx / d * side)


def plan_move(start, end, width, profile, rng=random, mode="aim", tempo=1.0, bounds=None):
    """Timestamped cursor positions from start to end; the last one is end.
    bounds = (screen width, height): keeps an overshoot off the bottom/right corners too."""
    hi_x, hi_y = (bounds[0] - 2, bounds[1] - 2) if bounds else (float("inf"), float("inf"))

    def px(p):
        return max(1, min(hi_x, round(p[0]))), max(1, min(hi_y, round(p[1])))

    dist = math.dist(start, end)
    if dist < 2:
        return [(0.0, *px(end))]

    mt = fitts_time(dist, width, profile) * tempo
    if mode == "reciprocal":
        mt *= RECIPROCAL_SPEEDUP
        correct = False
    else:
        correct = rng.random() < (0.85 if dist >= 2 * width else 0.2)

    if correct:
        reach = profile.reach_short if rng.random() < profile.undershoot_p else profile.reach_long
        aim = _along(start, end, reach + rng.uniform(-0.01, 0.01))
        primary_time = 0.75 * mt
    else:
        aim, primary_time = end, mt

    # Control points pushed 2× the bow: a cubic's peak deviation is well under its
    # control points' offset, so this makes `curvature` ≈ the actual sideways bow.
    bow = profile.curve_side * profile.curvature * dist * rng.uniform(0.5, 1.5) * 2
    cp1 = _along(start, aim, 0.3, bow)
    cp2 = _along(start, aim, 0.7, -bow * rng.uniform(0, 0.6))
    points = _segment(start, cp1, cp2, aim, primary_time, profile.peak_at, 0.0, rng)

    if correct:
        t1 = points[-1][0] + rng.uniform(*PAUSE)
        c1, c2 = _along(aim, end, 1 / 3), _along(aim, end, 2 / 3)
        points.append((t1, aim))      # still there when the correction starts
        points += _segment(aim, c1, c2, end, max(0.06, 0.25 * mt), CORRECTION_PEAK, t1, rng, first=False)

    return [(t, *px(p)) for t, p in points]
