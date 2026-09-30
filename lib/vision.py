"""
Pure screen-decision logic — no capture, no input, no config.

Every function takes plain data: frames are uint8 (h, w, 3) arrays in BGR
order (what np.array(mss_shot)[:, :, :3] gives), colours are (r, g, b), and
coordinates are frame-local — callers add the capture offset. Randomised
results take `rng` (anything with .triangular) so tests are deterministic.
Screen capture lives in lib/screen.py.
"""
import random

import numpy as np
from PIL import Image, ImageDraw


# ── Colour ────────────────────────────────────────────────────────────────────

def color_mask(frame, rgb, tol):
    """Boolean (h, w) mask of pixels within ±tol of rgb on every channel."""
    r, g, b = rgb
    return (
        (frame[:, :, 2] >= r - tol) & (frame[:, :, 2] <= r + tol) &
        (frame[:, :, 1] >= g - tol) & (frame[:, :, 1] <= g + tol) &
        (frame[:, :, 0] >= b - tol) & (frame[:, :, 0] <= b + tol)
    )


def color_close(rgb, expected, tol):
    """True if every channel of rgb is within ±tol of expected."""
    return all(abs(a - e) <= tol for a, e in zip(rgb, expected))


def polygon_mask(h, w, vertices):
    """Boolean (h, w) mask of the filled polygon (frame-local vertices)."""
    img = Image.new("L", (w, h), 0)
    ImageDraw.Draw(img).polygon(vertices, fill=1)
    return np.array(img, dtype=bool)


# ── Where to click ────────────────────────────────────────────────────────────

def click_point(xs, ys, jitter_pct, rng=random):
    """Centroid of the points, spread by a triangular jitter of ±jitter_pct of
    their bounding box — clicks land near the middle of a highlight."""
    mx, my = float(np.mean(xs)), float(np.mean(ys))
    sx = (float(xs.max()) - float(xs.min())) * jitter_pct
    sy = (float(ys.max()) - float(ys.min())) * jitter_pct
    return rng.triangular(mx - sx, mx + sx, mx), rng.triangular(my - sy, my + sy, my)


def locate(frame, rgb, tol, polygon=None, jitter_pct=0.25, rng=random):
    """(click point, matched pixel count) for rgb in the frame, optionally
    only inside `polygon`; (None, 0) if nothing matches."""
    mask = color_mask(frame, rgb, tol)
    if polygon is not None:
        mask &= polygon_mask(frame.shape[0], frame.shape[1], polygon)
    count = int(mask.sum())
    if count == 0:
        return None, 0
    ys, xs = np.where(mask)
    return click_point(xs, ys, jitter_pct, rng), count


# ── Clusters ──────────────────────────────────────────────────────────────────

def clusters(xs, ys, radius):
    """Greedy grouping of points: take the first remaining point as a seed; every
    remaining point within `radius` of that seed joins its cluster. Returns one
    boolean member mask (over the input points) per cluster, in seed order."""
    remaining = np.ones(len(xs), dtype=bool)
    groups = []
    while remaining.any():
        seed = int(np.argmax(remaining))
        members = remaining & ((xs - xs[seed]) ** 2 + (ys - ys[seed]) ** 2 <= radius ** 2)
        remaining &= ~members
        groups.append(members)
    return groups


def _matched_points(frame, rgb, tol):
    ys, xs = np.where(color_mask(frame, rgb, tol))
    return xs.astype(float), ys.astype(float)


def nearest_cluster_point(frame, rgb, tol, near, radius=30, jitter_pct=0.15, rng=random):
    """(click point in the cluster whose centroid is nearest `near`, total matched
    pixel count); ties go to the first cluster found. (None, 0) if no match."""
    xs, ys = _matched_points(frame, rgb, tol)
    if len(xs) == 0:
        return None, 0
    best, best_dist = None, float("inf")
    for members in clusters(xs, ys, radius):
        cx, cy = float(np.mean(xs[members])), float(np.mean(ys[members]))
        dist = (cx - near[0]) ** 2 + (cy - near[1]) ** 2
        if dist < best_dist:
            best, best_dist = members, dist
    return click_point(xs[best], ys[best], jitter_pct, rng), len(xs)


def count_clusters(frame, rgb, tol, radius):
    """Number of distinct rgb clusters (e.g. broken struts)."""
    return len(clusters(*_matched_points(frame, rgb, tol), radius))


def point_in_any_cluster(frame, rgb, tol, point, radius):
    """True if `point` lies inside the bounding box of any rgb cluster."""
    xs, ys = _matched_points(frame, rgb, tol)
    px, py = point
    for members in clusters(xs, ys, radius):
        cx, cy = xs[members], ys[members]
        if cx.min() <= px <= cx.max() and cy.min() <= py <= cy.max():
            return True
    return False
