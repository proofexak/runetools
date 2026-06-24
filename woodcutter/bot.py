import time
import random
import threading
import math
import ctypes
import os
import numpy as np
import pyautogui
import mss
from pynput import keyboard
from ultralytics import YOLO

# ── Config ────────────────────────────────────────────────────────────────────
MODEL_PATH  = os.path.join(os.path.dirname(__file__), "..", "models", "osrs_detector.pt")
GAME_REGION = None   # None = full screen; or (left, top, width, height) tuple
CONFIDENCE  = 0.5

TREE_CLASSES = {"tree"}
BANK_CLASS   = "bank_booth"

TOGGLE_KEY   = keyboard.KeyCode.from_char('p')

INVENTORY_REGION = (1692, 735, 189, 260)
INVENTORY_SLOTS  = 28

# Movement detection
MOVEMENT_REGION = (311, 174, 1177, 595)
MOVEMENT_THRESH = 3.0
MOVEMENT_STABLE = 3
MOVEMENT_POLL   = 0.15

# Tree-gone detection
TREE_POLL     = 2.0    # seconds between YOLO checks while chopping
CHOP_TIMEOUT  = 90.0   # max seconds to wait for a tree to disappear
SKIP_RADIUS   = 80     # px — same-tree dedup radius

# How many consecutive timeouts on the same tree before we blacklist it
MAX_FAILURES  = 2

# ── Toggle ────────────────────────────────────────────────────────────────────

_enabled = threading.Event()

def _on_press(key):
    if key == TOGGLE_KEY:
        if _enabled.is_set():
            _enabled.clear()
            print("\n[BOT PAUSED]  — press P to resume")
        else:
            _enabled.set()
            print("\n[BOT RESUMED] — press P to pause")

def start_hotkey_listener():
    listener = keyboard.Listener(on_press=_on_press)
    listener.daemon = True
    listener.start()

# ── Screen capture ────────────────────────────────────────────────────────────

def capture_screen(region=None):
    with mss.MSS() as sct:
        if region:
            monitor = {"left": region[0], "top": region[1],
                       "width": region[2], "height": region[3]}
        else:
            monitor = sct.monitors[1]
        shot = sct.grab(monitor)
        frame = np.array(shot)[:, :, :3]
        return frame, (monitor["left"], monitor["top"])

# ── Detection helpers ─────────────────────────────────────────────────────────

def get_detections(results, target_classes):
    hits = []
    for box in results[0].boxes:
        name = results[0].names[int(box.cls)]
        conf = float(box.conf)
        if conf < CONFIDENCE:
            continue
        if name.lower() not in {c.lower() for c in target_classes}:
            continue
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        hits.append(((x1 + x2) / 2, (y1 + y2) / 2, conf, name))
    return hits


def nearest_to(detections, origin):
    ox, oy = origin
    return min(detections, key=lambda d: (d[0] - ox) ** 2 + (d[1] - oy) ** 2)


def screen_center(frame):
    h, w = frame.shape[:2]
    return w / 2, h / 2

# ── Mouse ─────────────────────────────────────────────────────────────────────

def _set_cursor(x, y):
    ctypes.windll.user32.SetCursorPos(int(x), int(y))


def _ease_in_out(t):
    return t * t * (3.0 - 2.0 * t)


def _cubic_bezier(t, p0, cp1, cp2, p3):
    u = 1.0 - t
    x = u**3*p0[0] + 3*u**2*t*cp1[0] + 3*u*t**2*cp2[0] + t**3*p3[0]
    y = u**3*p0[1] + 3*u**2*t*cp1[1] + 3*u*t**2*cp2[1] + t**3*p3[1]
    return x, y


def human_move(x1, y1, x2, y2):
    dist     = math.hypot(x2 - x1, y2 - y1)
    duration = random.uniform(0.08, 0.18) + dist * 0.00035
    steps    = max(25, int(dist * 0.6))
    dx, dy   = x2 - x1, y2 - y1

    plen = math.hypot(-dy, dx)
    if plen > 0:
        px, py = -dy / plen, dx / plen
    else:
        px, py = 0.0, 0.0

    bulge = random.uniform(-0.25, 0.25) * dist
    cp1 = (x1 + dx * random.uniform(0.2, 0.4) + px * bulge,
           y1 + dy * random.uniform(0.2, 0.4) + py * bulge)
    cp2 = (x1 + dx * random.uniform(0.6, 0.8) + px * bulge * random.uniform(0.5, 1.0),
           y1 + dy * random.uniform(0.6, 0.8) + py * bulge * random.uniform(0.5, 1.0))

    p0, p3       = (x1, y1), (x2, y2)
    step_delay   = duration / steps

    for i in range(steps + 1):
        t = _ease_in_out(i / steps)
        mx, my = _cubic_bezier(t, p0, cp1, cp2, p3)
        if 0.1 < i / steps < 0.9:
            mx += random.gauss(0, 0.4)
            my += random.gauss(0, 0.4)
        _set_cursor(mx, my)
        time.sleep(step_delay)


def human_click(cx, cy, off_x=0, off_y=0):
    tx = round(cx + off_x + random.randint(-4, 4))
    ty = round(cy + off_y + random.randint(-4, 4))
    sx, sy = pyautogui.position()
    human_move(sx, sy, tx, ty)
    pyautogui.click()

# ── Movement detection ────────────────────────────────────────────────────────

def _grab_movement():
    with mss.MSS() as sct:
        r = MOVEMENT_REGION
        mon = {"left": r[0], "top": r[1], "width": r[2], "height": r[3]}
        shot = sct.grab(mon)
    return np.array(shot)[:, :, :3].mean(axis=2).astype(float)


def wait_until_stopped(timeout=15.0):
    """
    Block until background stops moving.
    Returns (reached, ever_moved): reached=True if stable, ever_moved=True if
    the character actually walked somewhere.
    """
    deadline     = time.time() + timeout
    stable_count = 0
    ever_moved   = False
    prev         = _grab_movement()

    while time.time() < deadline:
        time.sleep(MOVEMENT_POLL)
        curr = _grab_movement()
        diff = np.abs(curr - prev).mean()

        if diff > MOVEMENT_THRESH:
            stable_count = 0
            ever_moved   = True
            print(f"  [walking] diff={diff:.1f}", end="\r")
        else:
            stable_count += 1
            if stable_count >= MOVEMENT_STABLE:
                print("  Character stopped.        ")
                return True, ever_moved
        prev = curr

    print("  Movement timeout — proceeding anyway.")
    return False, ever_moved

# ── Tree-gone detection ───────────────────────────────────────────────────────

def wait_for_tree_gone(model, timeout=CHOP_TIMEOUT):
    """
    After the character has stopped at a tree:
      1. Fresh scan to find the nearest tree to screen centre (that's the one
         being chopped — (cx,cy) from the click is stale after a long walk).
      2. Poll until that tree disappears (stump / fully chopped).
    Returns True if tree gone, False if timeout.
    """
    frame, _ = capture_screen(GAME_REGION)
    results   = model(frame, verbose=False)
    trees     = get_detections(results, TREE_CLASSES)

    if not trees:
        print("  No tree visible after stopping — nothing to track.")
        return True

    cx_screen, cy_screen = screen_center(frame)
    chop_cx, chop_cy, _, _ = nearest_to(trees, (cx_screen, cy_screen))
    print(f"  Tracking tree at ({chop_cx:.0f}, {chop_cy:.0f})")

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(TREE_POLL)
        frame, _  = capture_screen(GAME_REGION)
        results   = model(frame, verbose=False)
        trees     = get_detections(results, TREE_CLASSES)

        still_there = any(
            math.hypot(t[0] - chop_cx, t[1] - chop_cy) < SKIP_RADIUS
            for t in trees
        )

        if not still_there:
            print("  Tree gone — fully chopped!")
            return True

        elapsed = CHOP_TIMEOUT - (deadline - time.time())
        print(f"  [chopping] {elapsed:.0f}s elapsed", end="\r")

    print("  Chop timeout — moving on.")
    return False

# ── Main loop ─────────────────────────────────────────────────────────────────

def _near_skipped(cx, cy, skipped):
    return any(math.hypot(cx - sx, cy - sy) < SKIP_RADIUS for sx, sy in skipped)


def chop_loop(model):
    pyautogui.FAILSAFE = True
    skipped  = set()               # trees confirmed too high / repeatedly failing
    failures = {}                  # (round_cx, round_cy) → failure count

    while True:
        _enabled.wait()
        frame, (off_x, off_y) = capture_screen(GAME_REGION)
        results = model(frame, verbose=False)
        trees   = get_detections(results, TREE_CLASSES)
        trees   = [t for t in trees if not _near_skipped(t[0], t[1], skipped)]

        if not trees:
            print("[CHOP] No usable tree found — retrying...")
            time.sleep(random.uniform(1.0, 1.5))
            continue

        cx_player, cy_player = screen_center(frame)
        cx, cy, conf, name   = nearest_to(trees, (cx_player, cy_player))
        print(f"[CHOP] {name} ({conf:.2f}) at ({cx:.0f}, {cy:.0f})")

        human_click(cx, cy, off_x, off_y)

        # Wait for character to arrive
        _, ever_moved = wait_until_stopped()

        if not ever_moved:
            # Character didn't move — either already adjacent (fine) or
            # server rejected the click. We'll know quickly from the
            # tree-gone check; if it times out, count as a failure.
            pass

        # Track the tree in its NEW screen position after the walk
        gone = wait_for_tree_gone(model)

        if not gone:
            key = (round(cx), round(cy))
            failures[key] = failures.get(key, 0) + 1
            if failures[key] >= MAX_FAILURES:
                print(f"  Tree at ({cx:.0f},{cy:.0f}) failed {MAX_FAILURES}x — blacklisting.")
                skipped.add(key)

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    model = YOLO(MODEL_PATH)
    start_hotkey_listener()
    print("Bot started — P to pause/resume, move mouse to top-left to stop.")
    chop_loop(model)


if __name__ == "__main__":
    main()