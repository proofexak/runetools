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


# ── Inventory ─────────────────────────────────────────────────────────────────

def filled_slot_count(frame, slots, bg_rgb, tol, box=7, min_pixels=5):
    """Number of inventory slots that hold an item: a slot is filled when at
    least `min_pixels` pixels of the 2*box square around its centre differ from
    the empty-slot colour by more than `tol` on any channel. Robust to small or
    bright icons whose average colour is close to the background."""
    br, bg, bb = bg_rgb
    filled = 0
    for x, y in slots:
        patch = frame[max(0, y - box):y + box, max(0, x - box):x + box].astype(int)
        if patch.size == 0:
            continue
        deviating = ((np.abs(patch[:, :, 2] - br) > tol) |
                     (np.abs(patch[:, :, 1] - bg) > tol) |
                     (np.abs(patch[:, :, 0] - bb) > tol))
        if int(deviating.sum()) >= min_pixels:
            filled += 1
    return filled


# ── Frame differences ─────────────────────────────────────────────────────────

def frame_difference(a, b):
    """Mean absolute difference of the two frames' grayscale (channel mean)."""
    return float(np.abs(a.mean(axis=2) - b.mean(axis=2)).mean())


def _summed_diff(before, after):
    return np.abs(before.astype(int) - after.astype(int)).sum(axis=2)


def changed_slot(before, after, slot_w=36, slot_h=32, min_score=1000):
    """Centre of the slot-sized window that changed most between the frames
    (scanned on a half-slot grid), or None if no window changed by min_score."""
    diff = _summed_diff(before, after)
    h, w = diff.shape
    best_score, best = 0, None
    for y in range(0, h - slot_h, slot_h // 2):
        for x in range(0, w - slot_w, slot_w // 2):
            score = int(diff[y:y + slot_h, x:x + slot_w].sum())
            if score > best_score:
                best_score, best = score, (x + slot_w // 2, y + slot_h // 2)
    if best is None or best_score < min_score:
        return None
    return best


def menu_origin(before, after, threshold=20, min_pixels=20):
    """Top-left of the area that changed (e.g. a right-click menu opening):
    pixels whose summed channel difference exceeds `threshold`. None unless
    more than `min_pixels` changed."""
    ys, xs = np.where(_summed_diff(before, after) > threshold)
    if len(ys) <= min_pixels:
        return None
    return int(xs.min()), int(ys.min())
