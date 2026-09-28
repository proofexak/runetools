"""
Varrock Exp miner actions — two-rock mining with shift-click drop.
"""
import time, random, sys, os
import pyautogui

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from lib.screen import find_color, pixel_matches
from lib.mouse import human_click, human_move, jitter, hesitate
from lib.camera import face
import lib.pause as pause
import miner.varrock_exp.config as config

ORE_POLL    = 1.0
ORE_TIMEOUT = 10.0


def orient_south():
    face("south", config)


def _click_rock(color, tol, label):
    hesitate()
    pos, _ = find_color(color, tol, region=config.ROCK_REGION, jitter_pct=0.10)
    if not pos:
        print(f"  No {label} rock found")
        return False
    human_click(*pos)
    time.sleep(random.uniform(0.2, 0.5))
    sx, sy = config.ORE_SLOT
    human_move(sx + random.randint(-6, 6), sy + 22 + random.randint(-5, 5))
    return True


def click_magenta_rock():
    return _click_rock(config.MAGENTA, config.MAGENTA_TOL, "magenta")


def click_blue_rock():
    return _click_rock(config.BLUE, config.BLUE_TOL, "blue")


def wait_and_drop():
    """Poll ORE_SLOT for up to 10s. Drop anything that isn't empty background."""
    sx, sy = config.ORE_SLOT
    _, _, bg = config.SLOT_BG_COLOR
    deadline = time.time() + ORE_TIMEOUT
    while time.time() < deadline:
        if pause.wait():
            deadline = time.time() + ORE_TIMEOUT   # time spent paused doesn't count
        if not pixel_matches(sx, sy, bg):
            print("  Item in slot — dropping")
            time.sleep(random.uniform(0.1, 0.35))
            pyautogui.keyDown("shift")
            time.sleep(random.uniform(0.08, 0.18))
            human_click(*jitter(sx, sy, n=6))
            time.sleep(random.uniform(0.05, 0.12))
            pyautogui.keyUp("shift")
            return True
        time.sleep(ORE_POLL)
    return False
