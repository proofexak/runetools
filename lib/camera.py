"""
Camera orientation via the compass — shared by all bots.

The config module passed in supplies COMPASS, MENU_HEADER, MENU_ROW_H and a
LOOK_<DIR>_ROW for each direction it uses (the compass right-click menu row).
"""
import time, random

from lib.mouse import human_click, human_right_click, menu_click, jitter, hesitate

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
