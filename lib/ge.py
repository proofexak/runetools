"""
Grand Exchange restock flow — sell leathers, buy hides.
Universal lib module; bots pass their own hide_type and on_complete callback.
"""
import time, random, sys, os
import pyautogui

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from lib.mouse    import smart_right_click, human_right_click, human_click, menu_click, \
                         jitter, human_typewrite, drag_and_drop
from lib.screen   import find_color, pixel_matches, grab
import lib.vision    as vision
from lib.movement import wait_until_stopped
import lib.pause     as pause
import lib.ge_config as cfg


# ── Internal helpers ──────────────────────────────────────────────────────────

def _wait_stopped():
    return wait_until_stopped(
        cfg.MOVEMENT_REGION, cfg.MOVEMENT_THRESH, cfg.MOVEMENT_STABLE,
        cfg.MOVEMENT_POLL, cfg.WALK_TIMEOUT, pause.wait,
    )


def _orient_west():
    cpx, cpy = jitter(*cfg.COMPASS, n=5)
    ax, ay = human_right_click(cpx, cpy)
    time.sleep(0.35)
    menu_click(ax + 5, ay + cfg.MENU_HEADER + cfg.LOOK_WEST_ROW * cfg.MENU_ROW_H + cfg.MENU_ROW_H // 2)
    time.sleep(0.5)


def _open_bank(region):
    """Find blue-hull banker in region, click, confirm bank opens. Returns True on success."""
    for attempt in range(cfg.MAX_BANKER_TRIES):
        pause.wait()
        pos, _ = find_color(cfg.BLUE, cfg.BLUE_TOL, region=region)
        if pos:
            human_click(*pos)
            bx, by, expected = cfg.BANK_CHECK
            deadline = time.time() + 5.0
            while time.time() < deadline:
                if pixel_matches(bx, by, expected):
                    return True
                time.sleep(0.3)
        print(f"  [GE] Banker not found (attempt {attempt+1})...")
        time.sleep(1.0)
    return False


def _open_ge():
    """Find magenta GE agent and confirm GE interface opens. Returns True on success."""
    for attempt in range(cfg.MAX_AGENT_TRIES):
        pause.wait()
        pos, _ = find_color(cfg.MAGENTA, cfg.MAGENTA_TOL, region=cfg.GE_REGION)
        if pos:
            human_click(*pos)
            gx, gy, expected = cfg.GE_CHECK
            deadline = time.time() + 5.0
            while time.time() < deadline:
                if pixel_matches(gx, gy, expected):
                    return True
                time.sleep(0.3)
        print(f"  [GE] Agent not found (attempt {attempt+1})...")
        time.sleep(1.0)
    return False


def _wait_offer():
    """Poll OFFER_COMPLETE pixel; click it when complete. Returns True or False."""
    cx, cy, expected = cfg.OFFER_COMPLETE
    for attempt in range(cfg.MAX_OFFER_TRIES):
        if pixel_matches(cx, cy, expected):
            human_click(*jitter(cx, cy))
            time.sleep(random.uniform(0.3, 0.5))
            return True
        delay = random.uniform(1.5, 2.5)
        print(f"  [GE] Offer not complete (attempt {attempt+1}), waiting {delay:.1f}s...")
        time.sleep(delay)
    return False


def _deposit_and_relocate():
    """Deposit all, find where hides landed via snapshot diff, drag to SECOND_BANK_TAB_SLOT."""
    l, t, _, _ = cfg.GE_BANK_AREA
    before, _ = grab(cfg.GE_BANK_AREA)
    human_click(*jitter(*cfg.DEPOSIT_BTN))
    time.sleep(random.uniform(0.7, 1.1))
    after, _ = grab(cfg.GE_BANK_AREA)

    slot = vision.changed_slot(before, after)
    if slot is None:
        print("  [GE] Could not detect changed bank slot.")
        return False
    best_cx, best_cy = l + slot[0], t + slot[1]

    print(f"  [GE] Hides at ({best_cx}, {best_cy}) — dragging to slot...")
    tx, ty = cfg.SECOND_TAB
    drag_and_drop(best_cx, best_cy, tx, ty)
    time.sleep(random.uniform(0.4, 0.7))
    human_click(*jitter(tx, ty))
    time.sleep(random.uniform(0.3, 0.5))
    return True


# ── Main GE attempt ───────────────────────────────────────────────────────────

def _ge_attempt(hide_type):
    """Single GE attempt. Returns True, 'retry', or 'fatal'."""

    # Step 1: Teleport to GE
    print("\n[GE] Step 1: Teleport to GE")
    pyautogui.press("escape")
    time.sleep(random.uniform(0.3, 0.5))
    pyautogui.press("f4")
    time.sleep(random.uniform(0.6, 1.0))
    _, _, mx, my = smart_right_click(*cfg.RING_SLOT, menu_scan_region=cfg.RING_MENU_REGION)
    time.sleep(random.uniform(0.35, 0.55))
    menu_click(mx + 5, my + cfg.MENU_HEADER + cfg.RING_MENU_ROW * cfg.MENU_ROW_H + cfg.MENU_ROW_H // 2)
    print("[GE] Waiting for teleport animation...")
    time.sleep(random.uniform(4.5, 5.5))

    # Step 2: Orient west
    print("[GE] Step 2: Orient west")
    _orient_west()

    # Steps 2a+3+4: Find banker in approach region, click, wait for bank to open
    print("[GE] Step 2a: Open bank via approach region")
    if not _open_bank(cfg.GE_APPROACH_REGION):
        print("[GE] Banker not found in approach region — retrying path...")
        return "retry"

    # Step 5: Second bank tab
    print("[GE] Step 5: Second bank tab")
    human_click(*jitter(*cfg.SECOND_TAB))
    time.sleep(random.uniform(0.3, 0.5))

    # Step 6: Enable notes
    print("[GE] Step 6: Enable notes")
    nx, ny, ncolor = cfg.NOTES_CHECK
    if not pixel_matches(nx, ny, ncolor):
        human_click(*jitter(*cfg.NOTES_BTN))
        time.sleep(random.uniform(0.3, 0.5))

    # Step 7: Withdraw from slot 1
    print("[GE] Step 7: Withdraw hides (noted)")
    human_click(*jitter(*cfg.BANK_SLOT_1))
    time.sleep(random.uniform(0.3, 0.5))

    # Step 7a: Disable notes
    print("[GE] Step 7a: Disable notes")
    human_click(*jitter(*cfg.NOTES_BTN))
    time.sleep(random.uniform(0.3, 0.5))

    # Step 8: Close bank
    pyautogui.press("escape")
    time.sleep(random.uniform(0.3, 0.5))

    # Step 9: Open GE
    print("[GE] Step 9: Opening GE")
    if not _open_ge():
        print("[GE] Could not open GE — stopping.")
        return "fatal"

    # Steps 10-14: Set up sell offer
    print("[GE] Step 10-14: Setting up sell offer")
    human_click(*jitter(*cfg.SELL_SLOT))
    time.sleep(random.uniform(0.4, 0.7))
    human_click(*jitter(*cfg.PRICE_BTN))
    time.sleep(random.uniform(0.3, 0.5))
    human_typewrite("1")
    pyautogui.press("enter")
    time.sleep(random.uniform(0.3, 0.5))
    human_click(*jitter(*cfg.CONFIRM_BTN))
    time.sleep(random.uniform(0.5, 0.8))
    human_click(*jitter(*cfg.SELL_YES_BTN))
    time.sleep(random.uniform(0.5, 0.8))

    # Step 15: Wait for sell
    print("[GE] Step 15: Waiting for sell to complete...")
    if not _wait_offer():
        print("[GE] Sell never completed — stopping.")
        return "fatal"

    # Step 16: Retrieve coins
    print("[GE] Step 16: Retrieve coins")
    human_click(*jitter(*cfg.RETRIEVE_SLOT_1))
    time.sleep(random.uniform(0.4, 0.7))

    # Steps 16a-e: Set up buy offer
    print("[GE] Step 16a-e: Setting up buy offer")
    human_click(*jitter(*cfg.BUY_BTN))
    time.sleep(random.uniform(0.5, 0.8))
    human_typewrite(hide_type)
    time.sleep(random.uniform(0.4, 0.7))
    human_click(*jitter(*cfg.BUY_SEARCH_RESULT))
    time.sleep(random.uniform(0.4, 0.7))
    human_click(*jitter(*cfg.BUY_QUANTITY_BTN))
    time.sleep(random.uniform(0.3, 0.5))
    human_typewrite(str(cfg.GE_QUANTITY))
    pyautogui.press("enter")
    time.sleep(random.uniform(0.3, 0.5))
    human_click(*jitter(*cfg.PRICE_BTN))
    time.sleep(random.uniform(0.3, 0.5))
    human_typewrite(str(cfg.GE_BUY_PRICE))
    pyautogui.press("enter")
    time.sleep(random.uniform(0.3, 0.5))
    human_click(*jitter(*cfg.CONFIRM_BTN))
    time.sleep(random.uniform(0.5, 0.8))

    # Step 16f: Wait for buy
    print("[GE] Step 16f: Waiting for buy to complete...")
    if not _wait_offer():
        print("[GE] Buy never completed — stopping.")
        return "fatal"

    # Step 16g: Retrieve hides
    print("[GE] Step 16g: Retrieve purchased hides")
    human_click(*jitter(*cfg.RETRIEVE_SLOT_1))
    time.sleep(random.uniform(0.3, 0.5))
    human_click(*jitter(*cfg.RETRIEVE_SLOT_2))
    time.sleep(random.uniform(0.3, 0.5))

    # Step 17: Close GE
    pyautogui.press("escape")
    time.sleep(random.uniform(0.3, 0.5))

    # Step 18: Bank again
    print("[GE] Step 18: Banking hides")
    if not _open_bank(cfg.GE_REGION):
        print("[GE] Could not open bank after GE — stopping.")
        return "fatal"

    # Step 19: Deposit and relocate
    print("[GE] Step 19: Deposit and relocate hides")
    if not _deposit_and_relocate():
        print("[GE] Failed to relocate hides — stopping.")
        return "fatal"

    pyautogui.press("escape")
    time.sleep(random.uniform(0.3, 0.5))
    return True


# ── Public entry point ────────────────────────────────────────────────────────

def run_ge_flow(hide_type, on_complete):
    """
    Full GE restock: teleport → sell leathers → buy hides → bank → on_complete().
    Returns True on success, False if bot should stop.
    """
    print("[GE] Starting in 3s — switch to OSRS.")
    time.sleep(3)
    for attempt in range(cfg.GE_MAX_RETRIES):
        result = _ge_attempt(hide_type)
        if result == "fatal":
            return False
        if result is True:
            print("[GE] Restock complete — calling on_complete...")
            return on_complete()
        print(f"[GE] Retrying ({attempt+1}/{cfg.GE_MAX_RETRIES})...")

    print("[GE] Max retries reached — stopping.")
    return False
