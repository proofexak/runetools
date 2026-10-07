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


def find_targets(frame, targets, radius=40, jitter_pct=0.25, rng=random):
    """What's visible, for a bot deciding where it is: `targets` maps a name to
    (rgb, tol, near) and each comes back as the click point (frame-local) of its
    rgb cluster nearest `near`, or None if that colour isn't in the frame."""
    return {name: nearest_cluster_point(frame, rgb, tol, near, radius=radius,
                                        jitter_pct=jitter_pct, rng=rng)[0]
            for name, (rgb, tol, near) in targets.items()}


def region_center(region):
    """Centre (x, y) of a (left, top, width, height) rect or of a polygon's bounding box."""
    if isinstance(region[0], (tuple, list)):
        xs, ys = [p[0] for p in region], [p[1] for p in region]
        return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    l, t, w, h = region
    return l + w / 2, t + h / 2


def blank_rects(frame, rects, origin=(0, 0)):
    """Copy of the frame with each (left, top, width, height) rect — in the same
    coordinates as `origin`, the frame's top-left — painted black, so nothing in
    it can match (e.g. the bot's own overlay window)."""
    out = frame.copy()
    h, w = out.shape[:2]
    for l, t, rw, rh in rects:
        x0, y0 = max(0, int(l - origin[0])), max(0, int(t - origin[1]))
        x1, y1 = min(w, int(l - origin[0] + rw)), min(h, int(t - origin[1] + rh))
        if x0 < x1 and y0 < y1:
            out[y0:y1, x0:x1] = 0
    return out


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


def menu_origin(before, after, threshold=20, min_pixels=20):
    """Top-left of the area that changed (e.g. a right-click menu opening):
    pixels whose summed channel difference exceeds `threshold`. None unless
    more than `min_pixels` changed."""
    ys, xs = np.where(_summed_diff(before, after) > threshold)
    if len(ys) <= min_pixels:
        return None
    return int(xs.min()), int(ys.min())


# ── Template matching ─────────────────────────────────────────────────────────

MIN_TEMPLATE_STD = 1.0   # a featureless template (e.g. all black) can't be located


def _gray(img):
    return img.astype(np.float64).mean(axis=2)


def find_template(frame, template, max_diff=8.0):
    """Frame-local centre of the window that best matches `template`, or None.
    Best = lowest sum of squared grayscale differences (FFT cross-correlation);
    accepted only if that window's mean absolute grayscale difference is
    <= max_diff. Featureless templates and templates larger than the frame
    never match."""
    th, tw = template.shape[:2]
    fh, fw = frame.shape[:2]
    if th > fh or tw > fw:
        return None
    t = _gray(template)
    if t.std() < MIN_TEMPLATE_STD:
        return None
    f = _gray(frame)

    # SSD(u, v) = sum(window²) - 2·corr(u, v) + sum(t²), over valid offsets only
    shape = (fh, fw)
    corr = np.fft.irfft2(np.fft.rfft2(f, shape) * np.conj(np.fft.rfft2(t, shape)), shape)
    corr = corr[:fh - th + 1, :fw - tw + 1]
    sq = np.pad(np.cumsum(np.cumsum(f * f, axis=0), axis=1), ((1, 0), (1, 0)))
    window_sq = sq[th:, tw:] - sq[:-th, tw:] - sq[th:, :-tw] + sq[:-th, :-tw]
    ssd = window_sq - 2 * corr + (t * t).sum()

    v, u = np.unravel_index(int(np.argmin(ssd)), ssd.shape)
    if np.abs(f[v:v + th, u:u + tw] - t).mean() > max_diff:
        return None
    return int(u + tw // 2), int(v + th // 2)
