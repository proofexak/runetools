"""
Human-like mouse input — plays lib/motion.py's move plans on a clock, Gaussian click
scatter, a dwell before each click, delays from lib/human.py (PRO-8).
Cross-platform (Windows/macOS/Linux) via pyautogui's cursor positioning.
"""
import time, random
import pyautogui
import lib.pause as pause
import lib.human as human
import lib.motion as motion


def _set_cursor(x, y):
    pyautogui.moveTo(int(x), int(y), _pause=False)


def _offset(width, rng=random):
    return motion.click_offset(width, human.active(), rng)


def _dwell(mode="aim"):
    time.sleep(motion.dwell(human.active(), mode=mode))


def _move(x2, y2, width=16, mode="aim"):
    """Move the cursor to (x2, y2) along a motion plan, each point at its planned time."""
    plan = motion.plan_move(pyautogui.position(), (x2, y2), width, human.active(),
                            mode=mode, tempo=human.tempo(), bounds=tuple(pyautogui.size()))
    t0 = time.perf_counter()
    for t, x, y in plan:
        wait = t0 + t - time.perf_counter()
        if wait > 0:
            time.sleep(wait)
        _set_cursor(x, y)


def human_move(x, y):
    """Move cursor to (x, y) with human-like motion, no click."""
    human.sleep(0.05, 0.15)
    _move(x + _offset(6), y + _offset(6))


def human_click(x, y):
    human.sleep(0.1, 0.18)
    _move(x + _offset(6), y + _offset(6))
    _dwell()
    pyautogui.click()


def human_right_click(x, y):
    """Returns the actual (ax, ay) click coordinates for accurate menu positioning."""
    human.sleep(0.1, 0.18)
    ax = x + _offset(6)
    ay = y + _offset(6)
    _move(ax, ay)
    _dwell()
    pyautogui.rightClick()
    return ax, ay


def smart_right_click(x, y, menu_scan_region=None):
    """Right-click and detect the actual menu position.
    menu_scan_region: (left, top, width, height) — small region where the menu appears.
    Scans that region for changed pixels after right-clicking.
    Falls back to click coords if detection fails.
    Returns (ax, ay, menu_x, menu_top_y).
    """
    from lib.screen import grab
    import lib.vision as vision

    ax = x + random.randint(-3, 3)
    ay = y + random.randint(-3, 3)

    if menu_scan_region is None:
        # Default: area above and around the click
        pad_x, pad_y = 60, 350
        sl, st = max(0, ax - pad_x), max(0, ay - pad_y)
        sw, sh = pad_x * 4, pad_y * 2
    else:
        sl, st, sw, sh = menu_scan_region

    before, _ = grab((sl, st, sw, sh))

    human.sleep(0.1, 0.18)
    _move(ax, ay)
    _dwell()
    pyautogui.rightClick()
    time.sleep(0.18)

    after, _ = grab((sl, st, sw, sh))

    origin = vision.menu_origin(before, after)
    if origin is not None:
        menu_left, menu_top = sl + origin[0], st + origin[1]
    else:
        print("  smart_right_click: menu not detected, using click coords as fallback")
        menu_top, menu_left = ay, ax

    return ax, ay, menu_left, menu_top


def human_press(key):
    """Press a key like a finger does: down, held ~110 ms (human.hold_time), up — never 0 ms."""
    pyautogui.keyDown(key)
    try:
        time.sleep(human.hold_time())
    finally:
        release_key(key)


def human_typewrite(text):
    """Type text a key at a time, each held like a finger (human_press), with skewed gaps.
    Pause/stop hotkeys are suppressed while typing (see pause.suppress_hotkeys)."""
    for char in text:
        pause.suppress_hotkeys(0.5)   # covers listener lag after the last key
        human_press("space" if char == " " else char)
        human.sleep(0.04, 0.12)


def drag_and_drop(from_x, from_y, to_x, to_y):
    """Click-hold-drag from one point to another."""
    _move(from_x, from_y)
    human.sleep(0.1, 0.2)
    pyautogui.mouseDown()
    human.sleep(0.1, 0.15)
    _move(to_x, to_y)
    human.sleep(0.1, 0.15)
    pyautogui.mouseUp()


def menu_click(x, y):
    """Click a context menu item: a wide, short target (30 × 4 px around the point)."""
    tx = x + _offset(30)
    human.sleep(0.1, 0.18)
    _move(tx, y + _offset(4))
    _dwell()
    pyautogui.click()


def jitter(x, y, n=8, rng=random):
    """A click point on a target n px either side of (x, y): Gaussian around the centre,
    SD ≈ (2n) / 4.1, never past ±n."""
    return x + _offset(2 * n, rng), y + _offset(2 * n, rng)


def release_key(key):
    """keyUp that still works during pyautogui's corner failsafe — the
    emergency abort must not leave a modifier held down."""
    failsafe = pyautogui.FAILSAFE
    pyautogui.FAILSAFE = False
    try:
        pyautogui.keyUp(key)
    finally:
        pyautogui.FAILSAFE = failsafe


def hesitate():
    """Short human-like pause before an action."""
    human.sleep(0.3, 0.8)


def quick_click(x, y):
    """Click for tight back-and-forth loops (e.g. knife ↔ chocolate bar): one fluid,
    faster move (motion's "reciprocal" mode), a short dwell, no pre-click pause."""
    jx, jy = jitter(x, y)
    _move(jx, jy, mode="reciprocal")
    _dwell("reciprocal")
    pyautogui.click(_pause=False)


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
