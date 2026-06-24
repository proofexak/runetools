"""
Al Kharid tanner bot actions — navigation, trading Ellis, banking.
Imports config from config.py and shared utilities from lib/.
"""
import time, random, sys, os
import pyautogui

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib.mouse    import human_click, human_move, human_right_click, menu_click, jitter, random_area_click
from lib.screen   import find_color, pixel_matches
from lib.movement import wait_until_stopped
import lib.pause as pause

from tanner.config import (
    HIDE_TYPE, BLUE, BLUE_TOL, MAGENTA, MAGENTA_TOL,
    ELLIS_REGION, BANK_REGION,
    MOVEMENT_REGION, MOVEMENT_THRESH, MOVEMENT_STABLE, MOVEMENT_POLL, WALK_TIMEOUT,
    INTERFACE_BUTTONS, INTERFACE_TOL, TANNING_CHECK,
    MENU_ROW_H, MENU_HEADER, COMPASS, CHARACTER, TANNER_AREA, LOOK_WEST_ROW,
    MAX_ELLIS_TRIES, MAX_ELLIS_ROUNDS, ELLIS_ROUND_WAIT,
    MAX_BANK_RETRIES, MAX_BOOTH_TRIES,
    BANK_CHECK, INVENTORY_CHECK, DEPOSIT_BTN, HIDE_SLOT, BANK_SLOT_2,
)


def _wait_stopped():
    return wait_until_stopped(
        MOVEMENT_REGION, MOVEMENT_THRESH, MOVEMENT_STABLE,
        MOVEMENT_POLL, WALK_TIMEOUT, pause.wait,
    )


def orient_west():
    """One-time camera orientation at session start."""
    print("  Orienting camera west...")
    cpx, cpy = jitter(*COMPASS, n=5)
    ax, ay = human_right_click(cpx, cpy)
    time.sleep(0.35)
    menu_click(ax + 5, ay + MENU_HEADER + LOOK_WEST_ROW * MENU_ROW_H + MENU_ROW_H // 2)
    time.sleep(0.5)


def inventory_open():
    ix, iy, icolor = INVENTORY_CHECK
    return pixel_matches(ix, iy, icolor, tol=INTERFACE_TOL)


def interface_open():
    tx, ty, tcolor = TANNING_CHECK
    return pixel_matches(tx, ty, tcolor, tol=INTERFACE_TOL)


def click_tan_all(timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        pause.wait()
        if interface_open():
            bx, by, _ = INTERFACE_BUTTONS[HIDE_TYPE]
            human_click(bx + random.randint(-12, 12), by + random.randint(-12, 12))
            return True
        time.sleep(0.2)
    print("  Tanning interface not detected.")
    return False


def walk_to_tanner():
    print("\n── Walk to tanner ──")
    pyautogui.press("escape")
    time.sleep(random.uniform(0.15, 0.3))
    if inventory_open():
        print("  Inventory open — closing...")
        pyautogui.press("escape")
        time.sleep(random.uniform(0.15, 0.25))
    random_area_click(TANNER_AREA)
    time.sleep(random.uniform(2.0, 4.0))
    human_move(
        CHARACTER[0] + random.randint(-52, 52),
        CHARACTER[1] + random.randint(-52, 52),
    )
    _wait_stopped()
    return True


def trade_ellis():
    print("\n[ELLIS] Hunting Ellis...")
    for round_ in range(1, MAX_ELLIS_ROUNDS + 1):
        for attempt in range(1, MAX_ELLIS_TRIES + 1):
            pause.wait()
            pos, _ = find_color(BLUE, BLUE_TOL, outside_pad=0, region=ELLIS_REGION)
            if not pos:
                print(f"  Round {round_} attempt {attempt}: not visible, waiting...")
                time.sleep(1.2)
                continue
            cx, cy = pos
            print(f"  Round {round_} attempt {attempt}: Ellis at ({cx:.0f}, {cy:.0f})")
            human_click(cx, cy)
            time.sleep(0.8)
            if click_tan_all():
                return True
            time.sleep(0.5)
        if round_ < MAX_ELLIS_ROUNDS:
            print(f"  Round {round_} exhausted — waiting {ELLIS_ROUND_WAIT}s...")
            time.sleep(ELLIS_ROUND_WAIT)
    print("  Failed to trade Ellis.")
    return False


def click_bank_booth():
    for attempt in range(MAX_BOOTH_TRIES):
        pause.wait()
        pos, _ = find_color(MAGENTA, MAGENTA_TOL, outside_pad=0, region=BANK_REGION)
        if pos:
            bx, by = pos
            print(f"  Booth at ({bx:.0f}, {by:.0f})")
            human_click(bx, by)
            _wait_stopped()
            return True
        print(f"  Booth not found (attempt {attempt+1}), retrying...")
        time.sleep(1.0)
    print("  Bank booth not found.")
    return False


def walk_to_bank():
    print("\n── Walk to bank ──")
    if click_bank_booth():
        return True
    print("  Bank booth not found.")
    return False


def bank_is_open(timeout=5.0):
    bx, by, expected = BANK_CHECK
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pixel_matches(bx, by, expected):
            return True
        time.sleep(0.3)
    return False


def do_bank():
    print("\n[BANK] Waiting for interface...")
    for retry in range(MAX_BANK_RETRIES):
        if bank_is_open():
            break
        print(f"  Bank didn't open (attempt {retry+1}) — re-clicking booth...")
        if not click_bank_booth():
            return False
    else:
        print("  Bank never opened.")
        return False

    time.sleep(0.5)
    print("  Depositing inventory...")
    human_click(*jitter(*DEPOSIT_BTN))
    time.sleep(0.6)

    _, _, empty_color = BANK_CHECK
    if pixel_matches(BANK_SLOT_2[0], BANK_SLOT_2[1], empty_color):
        print("  Bank slot 2 empty — all hides tanned!")
        pyautogui.press("escape")
        return "done"

    print("  Withdrawing hides...")
    human_click(*jitter(*HIDE_SLOT))
    time.sleep(0.4)

    pyautogui.press("escape")
    print("  Bank done.")
    return True
