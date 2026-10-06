"""
Al Kharid tanner bot actions — navigation, trading Ellis, banking.
Imports config from config.py and shared utilities from lib/.
"""
import time, random, sys, os
import pyautogui

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib.mouse    import human_click, human_move, human_right_click, menu_click, jitter, random_area_click
from lib.screen   import find_color, look_for, pixel_matches
from lib.movement import wait_until_stopped
from lib.camera import face
import lib.pause as pause
import lib.energy as energy

_need_hide_tab = True

import tanner.config as _cfg
from tanner.config import (
    BLUE, BLUE_TOL, MAGENTA, MAGENTA_TOL,
    ELLIS_REGION, BANK_REGION,
    MOVEMENT_REGION, MOVEMENT_THRESH, MOVEMENT_STABLE, MOVEMENT_POLL, WALK_TIMEOUT,
    INTERFACE_TOL, TANNING_CHECK,
    MENU_ROW_H, MENU_HEADER, CHARACTER, TANNER_AREA,
    AMULET_SLOT, AMULET_MENU_ROW, DOUBLE_DOORS_REGION, TP_BANK_REGION,
    MAX_ELLIS_TRIES, MAX_ELLIS_ROUNDS, ELLIS_ROUND_WAIT,
    MAX_BANK_RETRIES, MAX_BOOTH_TRIES,
    BANK_CHECK, INVENTORY_CHECK, DEPOSIT_BTN, HIDE_TAB, BANK_SLOT_1, BANK_SLOT_2,
    EMPTY_SLOT_CHECK,
)


def _wait_stopped():
    return wait_until_stopped(
        MOVEMENT_REGION, MOVEMENT_THRESH, MOVEMENT_STABLE,
        MOVEMENT_POLL, WALK_TIMEOUT,
    )


def orient_west():
    """Camera orientation at session start and after the recovery teleport."""
    face("west", _cfg)


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
            bx, by, _ = _cfg.INTERFACE_BUTTONS[_cfg.HIDE_TYPE]
            human_click(bx + random.randint(-12, 12), by + random.randint(-12, 12))
            return True
        time.sleep(0.2)
    print("  Tanning interface not detected.")
    return False


def walk_to_tanner():
    print("\n── Walk to tanner ──")
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
            last = round_ == MAX_ELLIS_ROUNDS and attempt == MAX_ELLIS_TRIES
            pos, _ = find_color(BLUE, BLUE_TOL, outside_pad=0, region=ELLIS_REGION, whole_screen=last)
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
        pos, _ = find_color(MAGENTA, MAGENTA_TOL, outside_pad=0, region=BANK_REGION,
                            whole_screen=attempt == MAX_BOOTH_TRIES - 1)
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


def _where(point):
    return f"at ({point[0]:.0f}, {point[1]:.0f})" if point else "not visible"


def look_around(need):
    """After a failed walk / trade / bank: one look at the whole screen for Ellis
    (blue) and the bank booth (purple), each the one nearest the character.
    need "ellis" (carrying hides): Ellis if seen — click him and tan → "tanned";
    else the booth — click it → "bank" (banking again puts the bot back on its
    usual spot). need "bank" (carrying leather): the booth → "bank".
    Nothing useful in sight → "lost" (the state table then uses the glory)."""
    print(f"\n[LOOK] Looking around for {'Ellis' if need == 'ellis' else 'the bank booth'}...")
    seen = look_for({"ellis": (BLUE, BLUE_TOL, CHARACTER), "booth": (MAGENTA, MAGENTA_TOL, CHARACTER)})
    ellis, booth = seen["ellis"], seen["booth"]
    print(f"  Ellis (blue) {_where(ellis)}, booth (purple) {_where(booth)}")

    if need == "ellis" and ellis:
        print("  Going to Ellis...")
        human_click(*ellis)
        _wait_stopped()
        if click_tan_all():
            return "tanned"
        print("  Ellis didn't open the tanning window.")
        return "lost"
    if booth:
        print("  Going to the bank booth...")
        human_click(*booth)
        _wait_stopped()
        return "bank"
    print("  Nothing useful in sight — glory recovery.")
    return "lost"


def recover():
    """Teleport to Al Kharid via amulet, walk to bank, do_bank. Returns True on success."""
    booth_region = getattr(_cfg, "TP_BOOTH_REGION", (0, 0, 0, 0))
    if not all(booth_region[2:]):
        print("[RECOVERY] TP Booth Region not calibrated (Tanning → ⚙ Configure) — recovery failed.")
        return False

    print("\n[RECOVERY] Escape...")
    pyautogui.press("escape")
    time.sleep(random.uniform(0.3, 0.5))

    print("[RECOVERY] Opening worn equipment (F4)...")
    pyautogui.press("f4")
    time.sleep(random.uniform(0.6, 1.0))

    print("[RECOVERY] Right-clicking amulet slot...")
    ax, ay = jitter(*AMULET_SLOT, n=3)
    ax, ay = human_right_click(ax, ay)
    time.sleep(random.uniform(0.35, 0.55))
    menu_click(ax + 5, ay + MENU_HEADER + AMULET_MENU_ROW * MENU_ROW_H + MENU_ROW_H // 2)

    print("[RECOVERY] Waiting for teleport...")
    time.sleep(random.uniform(2.5, 3.5))
    _wait_stopped()

    print("[RECOVERY] Orienting camera west...")
    orient_west()

    print("[RECOVERY] Clicking double doors...")
    random_area_click(DOUBLE_DOORS_REGION)
    time.sleep(random.uniform(0.5, 1.0))
    _wait_stopped()

    print("[RECOVERY] Walking into the bank...")
    random_area_click(TP_BANK_REGION)
    time.sleep(random.uniform(0.5, 1.0))
    _wait_stopped()

    print("[RECOVERY] Looking for bank booth...")
    for attempt in range(MAX_BOOTH_TRIES):
        pause.wait()
        pos, _ = find_color(MAGENTA, MAGENTA_TOL, outside_pad=0, region=booth_region,
                            whole_screen=attempt == MAX_BOOTH_TRIES - 1)
        if pos:
            bx, by = pos
            print(f"  [RECOVERY] Booth at ({bx:.0f}, {by:.0f})")
            human_click(bx, by)
            _wait_stopped()
            break
        print(f"  [RECOVERY] Booth not found (attempt {attempt+1})...")
        time.sleep(1.0)
    else:
        print("[RECOVERY] Could not find bank booth — recovery failed.")
        return False

    result = do_bank(skip_restock_check=True)
    if not result:
        print("[RECOVERY] Banking failed — recovery failed.")
        return False

    print("[RECOVERY] Complete.")
    return True


def bank_is_open(timeout=5.0):
    bx, by, expected = BANK_CHECK
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pixel_matches(bx, by, expected):
            return True
        time.sleep(0.3)
    return False


def do_bank(skip_restock_check=False):
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

    global _need_hide_tab
    time.sleep(0.5)
    if _need_hide_tab:
        print("  Switching to hide tab...")
        human_click(*jitter(*HIDE_TAB))
        time.sleep(0.4)
        _need_hide_tab = False
    print("  Depositing inventory...")
    human_click(*jitter(*DEPOSIT_BTN))
    time.sleep(0.6)

    stamina = energy.restock_stamina_at_bank(bank_open=bank_is_open)
    if stamina == energy.BANK_CLOSED:
        # the potion is still in the inventory: banking again (look around → booth) deposits it
        print("  Bank didn't reopen after the potion — banking failed.")
        return False
    if stamina:
        print("  Topped up stamina.")
        print("  Switching back to hide tab...")
        human_click(*jitter(*HIDE_TAB))
        time.sleep(1.4)

    # never click bank slots on the game world (and never read "slot 2 empty" off it)
    if not bank_is_open(timeout=2.0):
        print("  Bank isn't open — banking failed.")
        return False

    if not skip_restock_check:
        human_move(*jitter(*BANK_SLOT_1))
        time.sleep(0.6)
        _, _, empty_color = EMPTY_SLOT_CHECK
        bsx, bsy = BANK_SLOT_2
        if pixel_matches(bsx, bsy, empty_color):
            print("  Bank slot 2 empty — restocking from GE...")
            pyautogui.press("escape")
            return "restock"

    print("  Withdrawing hides...")
    human_click(*jitter(*BANK_SLOT_1))
    time.sleep(0.4)

    pyautogui.press("escape")
    print("  Bank done.")
    return True
