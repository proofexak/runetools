"""
Screen capture utilities — color scanning and pixel checking.
"""
import random
import numpy as np
import mss


def find_color(rgb, tol=10, outside_pad=0, region=None, jitter_pct=0.25):
    """
    Scan a screen region for pixels matching rgb (±tol).
    Returns (point, pixel_count) where point is a triangular-distributed random
    position within the matched bounding box, or (None, 0) if not found.

    region = (left, top, width, height)  — rectangle
    region = [(x1,y1), (x2,y2), ...]    — arbitrary polygon
    """
    r, g, b = rgb

    if isinstance(region[0], (tuple, list)):
        xs = [p[0] for p in region]
        ys = [p[1] for p in region]
        l, t = min(xs), min(ys)
        w, h = max(xs) - l, max(ys) - t
        local_verts = [(x - l, y - t) for x, y in region]
        use_poly = True
    else:
        l, t, w, h = region
        use_poly = False

    with mss.mss() as sct:
        mon   = sct.monitors[1]
        shot  = sct.grab({"left": mon["left"]+l, "top": mon["top"]+t, "width": w, "height": h})
        off_x = mon["left"] + l
        off_y = mon["top"]  + t

    frame = np.array(shot)[:, :, :3]  # BGR
    mask = (
        (frame[:, :, 2] >= r - tol) & (frame[:, :, 2] <= r + tol) &
        (frame[:, :, 1] >= g - tol) & (frame[:, :, 1] <= g + tol) &
        (frame[:, :, 0] >= b - tol) & (frame[:, :, 0] <= b + tol)
    )

    if use_poly:
        mask &= _poly_mask(frame.shape[0], frame.shape[1], local_verts)

    count = int(mask.sum())
    if count == 0:
        return None, 0
    ys_i, xs_i = np.where(mask)
    # Centroid of matched pixels = center of the outline shape.
    # Triangular spread over ±25% of bounding box keeps clicks natural.
    mx = float(np.mean(xs_i)) + off_x
    my = float(np.mean(ys_i)) + off_y
    sx = (int(xs_i.max()) - int(xs_i.min())) * jitter_pct
    sy = (int(ys_i.max()) - int(ys_i.min())) * jitter_pct
    cx = random.triangular(mx - sx, mx + sx, mx)
    cy = random.triangular(my - sy, my + sy, my)
    return (cx, cy), count


def find_nearest_color(rgb, tol=10, region=None, near=(0, 0), cluster_radius=30, jitter_pct=0.15):
    """
    Scan region for pixels matching rgb, then return the centroid of the cluster
    of matched pixels nearest to `near=(x, y)`. Useful when multiple distinct
    groups exist and you want the one closest to the player/character.
    Returns (point, pixel_count) or (None, 0).
    """
    r, g, b = rgb
    l, t, w, h = region
    with mss.mss() as sct:
        mon  = sct.monitors[1]
        shot = sct.grab({"left": mon["left"]+l, "top": mon["top"]+t, "width": w, "height": h})
        off_x = mon["left"] + l
        off_y = mon["top"]  + t

    frame = np.array(shot)[:, :, :3]
    mask = (
        (frame[:, :, 2] >= r - tol) & (frame[:, :, 2] <= r + tol) &
        (frame[:, :, 1] >= g - tol) & (frame[:, :, 1] <= g + tol) &
        (frame[:, :, 0] >= b - tol) & (frame[:, :, 0] <= b + tol)
    )
    count = int(mask.sum())
    if count == 0:
        return None, 0

    ys_i, xs_i = np.where(mask)
    abs_xs = xs_i.astype(float) + off_x
    abs_ys = ys_i.astype(float) + off_y

    # Cluster all pixels, pick the cluster whose centroid is nearest to `near`
    remaining = np.ones(len(abs_xs), dtype=bool)
    best_centroid = None
    best_dist = float('inf')
    best_arr = (None, None)

    while remaining.any():
        idx = int(np.argmax(remaining))
        sx_, sy_ = abs_xs[idx], abs_ys[idx]
        in_c = remaining & (
            (abs_xs - sx_) ** 2 + (abs_ys - sy_) ** 2 <= cluster_radius ** 2
        )
        remaining &= ~in_c
        cx_arr = abs_xs[in_c]
        cy_arr = abs_ys[in_c]
        cmx = float(np.mean(cx_arr))
        cmy = float(np.mean(cy_arr))
        d = (cmx - near[0]) ** 2 + (cmy - near[1]) ** 2
        if d < best_dist:
            best_dist = d
            best_centroid = (cmx, cmy)
            best_arr = (cx_arr, cy_arr)

    mx, my = best_centroid
    cx_arr, cy_arr = best_arr
    sx = (float(cx_arr.max()) - float(cx_arr.min())) * jitter_pct
    sy = (float(cy_arr.max()) - float(cy_arr.min())) * jitter_pct
    cx = random.triangular(mx - sx, mx + sx, mx)
    cy = random.triangular(my - sy, my + sy, my)
    return (cx, cy), count


def _poly_mask(h, w, vertices):
    from PIL import Image, ImageDraw
    img = Image.new('L', (w, h), 0)
    ImageDraw.Draw(img).polygon(vertices, fill=1)
    return np.array(img, dtype=bool)


def get_pixel_color(x, y):
    """Return the (r, g, b) color of a single screen pixel."""
    with mss.mss() as sct:
        shot = sct.grab({"left": x, "top": y, "width": 1, "height": 1})
    px = np.array(shot)[0, 0]
    return int(px[2]), int(px[1]), int(px[0])


def pixel_matches(x, y, expected_rgb, tol=15):
    """Check if a single screen pixel matches expected_rgb within tol."""
    r, g, b = get_pixel_color(x, y)
    er, eg, eb = expected_rgb
    return abs(r-er) <= tol and abs(g-eg) <= tol and abs(b-eb) <= tol
