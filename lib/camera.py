"""
Camera orientation via the compass — shared by all bots.

The config module passed in supplies COMPASS, MENU_HEADER, MENU_ROW_H and a
LOOK_<DIR>_ROW for each direction it uses (the compass right-click menu row).

zoom_out_top_down() sets the view the bots are calibrated for after a login
(lib/client.py): all the way zoomed out, looking straight down.
"""
import time, random

import pyautogui

from lib.mouse import human_click, human_right_click, human_move, menu_click, jitter, hesitate

ZOOM_NOTCHES = (40, 48)    # wheel notches down — more than the full zoom range
TILT_DRAG    = (220, 280)  # px dragged down with the middle button per pass
TILT_PASSES  = 2           # one pass didn't reach the steepest pitch; extra passes just overshoot

DIRECTIONS = ("north", "east", "south", "west")


def face(direction, cfg):
    """Turn the camera to face `direction`. North is a plain compass click."""
    if direction not in DIRECTIONS:
        raise ValueError(f"unknown direction {direction!r}")
    row = None if direction == "north" else getattr(cfg, f"LOOK_{direction.upper()}_ROW")

    print(f"  Orienting camera {direction}...")
    hesitate()
    cx, cy = jitter(*cfg.COMPASS, n=5)
    if row is None:
        human_click(cx, cy)
    else:
        ax, ay = human_right_click(cx, cy)
        time.sleep(random.uniform(0.25, 0.45))
        menu_click(ax + 5, ay + cfg.MENU_HEADER + row * cfg.MENU_ROW_H + cfg.MENU_ROW_H // 2)
    time.sleep(random.uniform(0.4, 0.7))


def zoom_out_top_down(x, y, rng=random):
    """With the mouse over the game view at (x, y): wheel down to zoom all the
    way out, then middle-drag down to tilt the camera to look from the top.
    Both overshoot on purpose — the game stops at its limits."""
    print("  Camera: zoom out, top-down...")
    human_move(x, y)
    for _ in range(rng.randint(*ZOOM_NOTCHES)):
        pyautogui.scroll(-1)
        time.sleep(rng.uniform(0.03, 0.08))
    for _ in range(TILT_PASSES):
        time.sleep(rng.uniform(0.2, 0.4))
        sx = x + rng.randint(-15, 15)
        human_move(sx, y + rng.randint(-10, 10))
        pyautogui.mouseDown(button="middle")
        try:   # nearly vertical: a sideways drag would also rotate the camera
            human_move(sx + rng.randint(-3, 3), y + rng.randint(*TILT_DRAG))
        finally:
            pyautogui.mouseUp(button="middle")
    time.sleep(rng.uniform(0.3, 0.6))
