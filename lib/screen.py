"""
Screen capture — grab regions of the screen and hand them to lib/vision.py,
which holds all the decision logic (colour matching, clustering, click points).

Whole-screen last try: find_color / find_nearest_color take whole_screen=True
for a bot's final attempt at a click target (Ellis, a bank booth, the GE
agent, ...). If the colour isn't in its usual region, the whole of monitor 1 is
searched once and the matching cluster nearest the region is used — so a
camera that drifted or a target that wandered off its calibrated area doesn't
stop the bot. Areas registered with exclude() (the bot's own overlay) are never
matched. Not for "is it still there?" checks (a respawning rock or vein must
read as gone, not be found somewhere else).
"""
import random
import numpy as np
import mss

import lib.vision as vision

WHOLE_SCREEN_CLUSTER_RADIUS = 40
_excluded = {}   # name -> (left, top, width, height), monitor-1 coords


def exclude(name, rect):
    """Never match anything inside rect in a whole-screen search (None removes it).
    The overlay registers its window here whenever it moves or resizes."""
    if rect is None:
        _excluded.pop(name, None)
    else:
        _excluded[name] = tuple(rect)


def screen_rect():
    """The whole of monitor 1 as a region."""
    with mss.mss() as sct:
        mon = sct.monitors[1]
        return 0, 0, mon["width"], mon["height"]


def _whole_screen():
    """(frame, offset) of all of monitor 1, with the excluded areas painted black."""
    rect = screen_rect()
    frame, offset = grab(rect)
    return vision.blank_rects(frame, list(_excluded.values()), origin=(rect[0], rect[1])), offset


def look_for(targets, jitter_pct=0.25):
    """One look at the whole screen (minus excluded areas) for several colours,
    for a bot working out where it is: `targets` maps a name to (rgb, tol, near)
    and each comes back as a screen point in its cluster nearest `near`, or None."""
    frame, (off_x, off_y) = _whole_screen()
    local = {name: (rgb, tol, (near[0] - off_x, near[1] - off_y)) for name, (rgb, tol, near) in targets.items()}
    found = vision.find_targets(frame, local, radius=WHOLE_SCREEN_CLUSTER_RADIUS, jitter_pct=jitter_pct, rng=random)
    return {name: None if p is None else (p[0] + off_x, p[1] + off_y) for name, p in found.items()}


def find_color_anywhere(rgb, tol=10, near=(0, 0), jitter_pct=0.25):
    """Search the whole screen (minus excluded areas) for rgb; return a point in
    the matching cluster nearest `near`, as (point, pixel_count) or (None, 0)."""
    frame, (off_x, off_y) = _whole_screen()
    point, count = vision.nearest_cluster_point(
        frame, rgb, tol, (near[0] - off_x, near[1] - off_y),
        radius=WHOLE_SCREEN_CLUSTER_RADIUS, jitter_pct=jitter_pct, rng=random)
    if point is None:
        print("  [screen] not on the whole screen either")
        return None, 0
    point = (point[0] + off_x, point[1] + off_y)
    print(f"  [screen] outside its usual area — found on the whole screen at ({point[0]:.0f}, {point[1]:.0f})")
    return point, count


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


def find_color(rgb, tol=10, outside_pad=0, region=None, jitter_pct=0.25, whole_screen=False):
    """
    Scan a screen region for pixels matching rgb (±tol).
    Returns (point, pixel_count) where point is a triangular-distributed random
    position around the matched pixels' centroid, or (None, 0) if not found.
    whole_screen: if it isn't in the region, search the whole screen once
    (find_color_anywhere, nearest the region's centre) — for a final attempt.

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
        if whole_screen:
            return find_color_anywhere(rgb, tol, near=vision.region_center(region), jitter_pct=jitter_pct)
        return None, 0
    return (point[0] + off_x, point[1] + off_y), count


def find_nearest_color(rgb, tol=10, region=None, near=(0, 0), cluster_radius=30, jitter_pct=0.15,
                       whole_screen=False):
    """
    Scan region for pixels matching rgb, then return a point in the cluster of
    matched pixels nearest to `near=(x, y)`. Useful when multiple distinct
    groups exist and you want the one closest to the player/character.
    Returns (point, pixel_count) or (None, 0).
    whole_screen: if none is in the region, search the whole screen once,
    still nearest `near` — for a final attempt.
    """
    frame, (off_x, off_y) = grab(region)
    point, count = vision.nearest_cluster_point(
        frame, rgb, tol, (near[0] - off_x, near[1] - off_y),
        radius=cluster_radius, jitter_pct=jitter_pct, rng=random)
    if point is None:
        if whole_screen:
            return find_color_anywhere(rgb, tol, near=near, jitter_pct=jitter_pct)
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
