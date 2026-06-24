"""
Human-like mouse input — bezier curves, jitter, randomized timing.
Works on Windows (uses SetCursorPos for sub-pixel accuracy).
"""
import time, random, math, ctypes
import pyautogui


def _set_cursor(x, y):
    ctypes.windll.user32.SetCursorPos(int(x), int(y))


def _make_ease():
    exp = random.uniform(1.5, 3.5)
    def _ease(t):
        return t**exp / (t**exp + (1 - t)**exp)
    return _ease


def _bezier(t, p0, cp1, cp2, p3):
    u = 1 - t
    return (u**3*p0[0] + 3*u**2*t*cp1[0] + 3*u*t**2*cp2[0] + t**3*p3[0],
            u**3*p0[1] + 3*u**2*t*cp1[1] + 3*u*t**2*cp2[1] + t**3*p3[1])


def _move(x2, y2):
    ease = _make_ease()
    x1, y1 = pyautogui.position()
    dist = math.hypot(x2-x1, y2-y1)
    steps = max(25, int(dist * 0.6))
    dur   = random.uniform(0.08, 0.18) + dist * 0.00035
    dx, dy = x2-x1, y2-y1
    plen = math.hypot(-dy, dx)
    px, py = (-dy/plen, dx/plen) if plen > 0 else (0, 0)
    bulge = random.uniform(-0.25, 0.25) * dist
    cp1 = (x1+dx*random.uniform(0.2,0.4)+px*bulge,   y1+dy*random.uniform(0.2,0.4)+py*bulge)
    cp2 = (x1+dx*random.uniform(0.6,0.8)+px*bulge*random.uniform(0.5,1),
           y1+dy*random.uniform(0.6,0.8)+py*bulge*random.uniform(0.5,1))
    for i in range(steps+1):
        t = ease(i/steps)
        mx, my = _bezier(t, (x1,y1), cp1, cp2, (x2,y2))
        if 0.1 < i/steps < 0.9:
            mx += random.gauss(0, 0.4)
            my += random.gauss(0, 0.4)
        _set_cursor(mx, my)
        time.sleep(dur/steps)


def human_move(x, y):
    """Move cursor to (x, y) with human-like motion, no click."""
    time.sleep(random.uniform(0.05, 0.15))
    _move(x + random.randint(-3, 3), y + random.randint(-3, 3))


def human_click(x, y):
    time.sleep(random.uniform(0.1, 0.18))
    _move(x + random.randint(-3, 3), y + random.randint(-3, 3))
    time.sleep(random.uniform(0.08, 0.2))
    pyautogui.click()


def human_right_click(x, y):
    """Returns the actual (ax, ay) click coordinates for accurate menu positioning."""
    time.sleep(random.uniform(0.1, 0.18))
    ax = x + random.randint(-3, 3)
    ay = y + random.randint(-3, 3)
    _move(ax, ay)
    time.sleep(random.uniform(0.08, 0.2))
    pyautogui.rightClick()
    return ax, ay


def menu_click(x, y):
    """Click a context menu item with x-jitter and a hover pause."""
    tx = x + random.randint(-15, 15)
    time.sleep(random.uniform(0.1, 0.18))
    _move(tx, y + random.randint(-2, 2))
    time.sleep(random.uniform(0.15, 0.25))
    pyautogui.click()


def jitter(x, y, n=8):
    return x + random.randint(-n, n), y + random.randint(-n, n)


def _in_polygon(x, y, poly):
    """Ray-casting point-in-polygon test."""
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i];  xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def random_area_click(region):
    """Click a random point inside a rectangle (left,top,w,h) or polygon [(x,y),...]."""
    if isinstance(region, (list, tuple)) and region and isinstance(region[0], (list, tuple)):
        xs = [p[0] for p in region];  ys = [p[1] for p in region]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        for _ in range(200):
            x = random.uniform(min_x, max_x)
            y = random.uniform(min_y, max_y)
            if _in_polygon(x, y, region):
                break
        else:  # fallback: centroid
            x, y = sum(xs) / len(xs), sum(ys) / len(ys)
    else:
        left, top, width, height = region
        x = random.triangular(left, left + width,  left + width  // 2)
        y = random.triangular(top,  top  + height, top  + height // 2)
    human_click(x, y)
