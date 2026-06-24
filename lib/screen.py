"""
Screen capture utilities — color scanning and pixel checking.
"""
import random
import numpy as np
import mss


def find_color(rgb, tol=10, outside_pad=0, region=None):
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

    with mss.MSS() as sct:
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
    print(f"  spread x:{int(xs_i.min())+off_x}-{int(xs_i.max())+off_x} "
          f"y:{int(ys_i.min())+off_y}-{int(ys_i.max())+off_y} ({count}px)")
    idx = random.randint(0, count - 1)
    return (int(xs_i[idx]) + off_x, int(ys_i[idx]) + off_y), count


def _poly_mask(h, w, vertices):
    from PIL import Image, ImageDraw
    img = Image.new('L', (w, h), 0)
    ImageDraw.Draw(img).polygon(vertices, fill=1)
    return np.array(img, dtype=bool)


def pixel_matches(x, y, expected_rgb, tol=15):
    """Check if a single screen pixel matches expected_rgb within tol."""
    with mss.MSS() as sct:
        shot = sct.grab({"left": x, "top": y, "width": 1, "height": 1})
    px = np.array(shot)[0, 0]
    r, g, b = int(px[2]), int(px[1]), int(px[0])
    er, eg, eb = expected_rgb
    return abs(r-er) <= tol and abs(g-eg) <= tol and abs(b-eb) <= tol
