"""
Screen capture — grab regions of the screen and hand them to lib/vision.py,
which holds all the decision logic (colour matching, clustering, click points).
"""
import random
import numpy as np
import mss

import lib.vision as vision


def grab(region, absolute=False):
    """Capture region (left, top, width, height), relative to monitor 1 — or to
    the virtual screen if absolute (movement and single-pixel reads have always
    used absolute coordinates; identical on a single monitor).
    Returns (frame, (off_x, off_y)): a BGR frame and the screen position of
    its top-left pixel, to turn frame-local results back into screen coords."""
    l, t, w, h = region
    with mss.mss() as sct:
        if not absolute:
            mon = sct.monitors[1]
            l, t = mon["left"] + l, mon["top"] + t
        shot = sct.grab({"left": l, "top": t, "width": w, "height": h})
        return np.array(shot)[:, :, :3], (l, t)


def find_color(rgb, tol=10, outside_pad=0, region=None, jitter_pct=0.25):
    """
    Scan a screen region for pixels matching rgb (±tol).
    Returns (point, pixel_count) where point is a triangular-distributed random
    position around the matched pixels' centroid, or (None, 0) if not found.

    region = (left, top, width, height)  — rectangle
    region = [(x1,y1), (x2,y2), ...]    — arbitrary polygon
    """
    polygon = None
    if isinstance(region[0], (tuple, list)):
        xs = [p[0] for p in region]
        ys = [p[1] for p in region]
        l, t = min(xs), min(ys)
        rect = (l, t, max(xs) - l, max(ys) - t)
        polygon = [(x - l, y - t) for x, y in region]
    else:
        rect = region

    frame, (off_x, off_y) = grab(rect)
    point, count = vision.locate(frame, rgb, tol, polygon=polygon, jitter_pct=jitter_pct, rng=random)
    if point is None:
        return None, 0
    return (point[0] + off_x, point[1] + off_y), count


def find_nearest_color(rgb, tol=10, region=None, near=(0, 0), cluster_radius=30, jitter_pct=0.15):
    """
    Scan region for pixels matching rgb, then return a point in the cluster of
    matched pixels nearest to `near=(x, y)`. Useful when multiple distinct
    groups exist and you want the one closest to the player/character.
    Returns (point, pixel_count) or (None, 0).
    """
    frame, (off_x, off_y) = grab(region)
    point, count = vision.nearest_cluster_point(
        frame, rgb, tol, (near[0] - off_x, near[1] - off_y),
        radius=cluster_radius, jitter_pct=jitter_pct, rng=random)
    if point is None:
        return None, 0
    return (point[0] + off_x, point[1] + off_y), count


def get_pixel_color(x, y):
    """Return the (r, g, b) color of a single screen pixel."""
    frame, _ = grab((x, y, 1, 1), absolute=True)
    b, g, r = frame[0, 0]
    return int(r), int(g), int(b)


def pixel_matches(x, y, expected_rgb, tol=15):
    """Check if a single screen pixel matches expected_rgb within tol."""
    return vision.color_close(get_pixel_color(x, y), expected_rgb, tol)
