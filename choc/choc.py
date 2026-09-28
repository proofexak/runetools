"""
Chocolate dust grinding — withdraw/grind/deposit loop, plus a GE restock
(sell accumulated dust, buy more bars) run periodically from choc/run.py.
"""
import time, random
import pyautogui

from lib.mouse import human_click, jitter, quick_click, human_typewrite
from lib.screen import find_color, pixel_matches
import choc.config as cfg
import lib.ge_config as ge_cfg


def open_bank():
    """Find + click the blue banker/booth, confirm it opened. Skips the
    find+click entirely if the bank's already open. Retries the whole
    find-click-confirm cycle a few times — the booth can be briefly
    obscured or the bank slow to open, which is what killed batch 2 in
    testing (single attempt, gave up immediately)."""
    bx2, by2, expected = cfg.BANK_CHECK

    if pixel_matches(bx2, by2, expected):
        return True

    for attempt in range(cfg.BANK_OPEN_RETRIES):
        pos, _ = find_color(cfg.BLUE, cfg.BLUE_TOL, outside_pad=0,
                             region=cfg.BANK_BOOTH_REGION)
        if pos:
            bx, by = pos
            human_click(bx, by)
            deadline = time.time() + cfg.BANK_OPEN_TIMEOUT
            while True:
                if pixel_matches(bx2, by2, expected):
                    return True
                if time.time() >= deadline:
                    break
                time.sleep(0.3)
            print(f"   Bank did not open (attempt {attempt + 1}/{cfg.BANK_OPEN_RETRIES}).")
        else:
            print(f"   Bank booth not found (attempt {attempt + 1}/{cfg.BANK_OPEN_RETRIES}).")
        time.sleep(1.0)

    return False


def withdraw_choc():
    """Withdraw one batch of chocolate bars. Assumes the bank is open and
    already on the chocolate tab."""
    print("   Withdrawing chocolate...")
    human_click(*jitter(*cfg.CHOC_BANK_SLOT))
    time.sleep(0.6)


def close_bank():
    """Escape to close the bank, then verify the inventory panel is
    actually showing — if escape didn't register, the grind loop's clicks
    would land on the still-open bank UI instead of the knife/chocolate."""
    pyautogui.press("escape")
    time.sleep(0.5)

    ix, iy, icolor = cfg.INVENTORY_CHECK
    if pixel_matches(ix, iy, icolor):
        return
    print("   Inventory not open — pressing Escape again.")
    pyautogui.press("escape")
    time.sleep(0.4)


def bootstrap_withdraw():
    """Called once at session start: open the bank, withdraw the first
    batch, close. Every later withdrawal piggybacks on that batch's
    deposit inside run_sequence(), so the booth is only ever clicked once
    per bank visit — never once to withdraw and again to deposit."""
    print("Opening bank...")
    if not open_bank():
        return False
    withdraw_choc()
    print("Closing bank...")
    close_bank()
    return True


def run_sequence(withdraw_next=True):
    """Grind, then a single bank visit: deposit the dust, withdraw the next
    batch (unless the caller already knows a restock is coming right after
    this — restock_ge() does its own withdraw at the end of its bank visit,
    so withdrawing here too would just get redeposited moments later)."""
    print(f"Grinding chocolate x{cfg.GRIND_COUNT}...")
    for i in range(cfg.GRIND_COUNT):
        quick_click(*cfg.KNIFE_SLOT)
        time.sleep(random.uniform(0.07, 0.1125))
        quick_click(*cfg.CHOC_INV_SLOT)
        time.sleep(random.uniform(0.127, 0.183))
        print(f"   {i + 1}/{cfg.GRIND_COUNT}")

    print("Opening bank...")
    if not open_bank():
        return False

    print("   Depositing dust...")
    human_click(*jitter(*cfg.DEPOSIT_BTN))
    time.sleep(0.6)

    if withdraw_next:
        withdraw_choc()

    print("Closing bank...")
    close_bank()

    print("Sequence complete.")
    return True


def _open_ge():
    """Find the magenta GE agent, click, confirm the GE interface opened.
    All positions/colours come from lib.ge_config — the GE interface itself
    is universal across bots, only GE_BUY_PRICE is choc-tuned (via
    choc/config_editor.py's "GE:" prefix)."""
    gx, gy, expected = ge_cfg.GE_CHECK
    for attempt in range(ge_cfg.MAX_AGENT_TRIES):
        pos, _ = find_color(ge_cfg.MAGENTA, ge_cfg.MAGENTA_TOL, region=ge_cfg.GE_REGION)
        if pos:
            human_click(*pos)
            deadline = time.time() + 5.0
            while True:
                if pixel_matches(gx, gy, expected):
                    return True
                if time.time() >= deadline:
                    break
                time.sleep(0.3)
            print(f"   GE did not open (attempt {attempt + 1}/{ge_cfg.MAX_AGENT_TRIES}).")
        else:
            print(f"   GE agent not found (attempt {attempt + 1}/{ge_cfg.MAX_AGENT_TRIES}).")
        time.sleep(1.0)
    return False


def _wait_offer():
    """Poll OFFER_COMPLETE pixel; click it once the offer finishes. Offers
    can take a while to fill (especially buys at market price), so this
    waits much longer than a UI-open check — OFFER_WAIT_TRIES is choc's
    own behavioural setting, not shared GE config, so it doesn't affect
    tanner's much shorter GE offer wait."""
    cx, cy, expected = ge_cfg.OFFER_COMPLETE
    for attempt in range(cfg.OFFER_WAIT_TRIES):
        # Wider tolerance than pixel_matches' default ±15 — live samples of
        # this pixel while genuinely complete varied by 17 in the green
        # channel alone (rendering/animation variance), which the default
        # wouldn't even have covered.
        if pixel_matches(cx, cy, expected, tol=30):
            human_click(*jitter(cx, cy))
            time.sleep(random.uniform(0.3, 0.5))
            return True
        delay = random.uniform(3.0, 5.0)
        print(f"   Offer not complete (attempt {attempt + 1}/{cfg.OFFER_WAIT_TRIES}), waiting {delay:.1f}s...")
        time.sleep(delay)
    return False


def restock_ge(quantity):
    """Sell accumulated chocolate dust and buy `quantity` more chocolate
    bars at the GE, then bank the bars. No teleport/orient — the grind spot
    is already within reach of both the bank and the GE. `quantity` is the
    bar count the session started with, so restocking always brings the
    bank back up to that same starting amount."""

    print("Restock: opening bank...")
    if not open_bank():
        return False

    print("   Switching to chocolate tab...")
    human_click(*jitter(*cfg.CHOCOLATE_TAB))
    time.sleep(random.uniform(0.3, 0.5))

    print("   Enabling notes...")
    nx, ny, ncolor = ge_cfg.NOTES_CHECK
    if not pixel_matches(nx, ny, ncolor):
        human_click(*jitter(*ge_cfg.NOTES_BTN))
        time.sleep(random.uniform(0.3, 0.5))

    print("   Withdrawing dust...")
    human_click(*jitter(*cfg.DUST_BANK_SLOT))
    time.sleep(random.uniform(0.3, 0.5))

    print("   Disabling notes...")
    human_click(*jitter(*ge_cfg.NOTES_BTN))
    time.sleep(random.uniform(0.3, 0.5))

    print("Restock: closing bank...")
    close_bank()

    print("Restock: opening GE...")
    if not _open_ge():
        print("   Could not open GE.")
        return False

    print("   Selling dust...")
    human_click(*jitter(*ge_cfg.SELL_SLOT))
    time.sleep(random.uniform(0.4, 0.7))
    human_click(*jitter(*ge_cfg.PRICE_BTN))
    # Longer pause than a plain click-to-click gap — the price box is a
    # popup text field that needs a moment to actually open and grab focus.
    # A single-character "1" types near-instantly once started, so if this
    # fires before the box is focused, the keystrokes (and the following
    # Enter) go wherever focus actually is instead — e.g. public chat.
    time.sleep(random.uniform(0.7, 1.0))
    human_typewrite("1")
    pyautogui.press("enter")
    time.sleep(random.uniform(0.3, 0.5))
    human_click(*jitter(*ge_cfg.CONFIRM_BTN))
    time.sleep(random.uniform(0.5, 0.8))
    human_click(*jitter(*ge_cfg.SELL_YES_BTN))
    time.sleep(random.uniform(0.5, 0.8))

    print("   Waiting for sell to complete...")
    if not _wait_offer():
        print("   Sell never completed.")
        return False

    print("   Retrieving coins...")
    human_click(*jitter(*ge_cfg.RETRIEVE_SLOT_1))
    time.sleep(random.uniform(0.4, 0.7))

    print("   Buying chocolate bars...")
    human_click(*jitter(*ge_cfg.BUY_BTN))
    time.sleep(random.uniform(0.5, 0.8))
    human_typewrite("chocolate bar")
    time.sleep(random.uniform(0.4, 0.7))
    human_click(*jitter(*ge_cfg.BUY_SEARCH_RESULT))
    time.sleep(random.uniform(0.4, 0.7))
    human_click(*jitter(*ge_cfg.BUY_QUANTITY_BTN))
    time.sleep(random.uniform(0.7, 1.0))
    human_typewrite(str(quantity))
    pyautogui.press("enter")
    time.sleep(random.uniform(0.3, 0.5))
    human_click(*jitter(*ge_cfg.PRICE_BTN))
    time.sleep(random.uniform(0.7, 1.0))
    human_typewrite(str(ge_cfg.GE_BUY_PRICE))
    pyautogui.press("enter")
    time.sleep(random.uniform(0.3, 0.5))
    human_click(*jitter(*ge_cfg.CONFIRM_BTN))
    time.sleep(random.uniform(0.5, 0.8))

    print("   Waiting for buy to complete...")
    if not _wait_offer():
        print("   Buy never completed.")
        return False

    print("   Retrieving purchased bars...")
    human_click(*jitter(*ge_cfg.RETRIEVE_SLOT_1))
    time.sleep(random.uniform(0.3, 0.5))
    human_click(*jitter(*ge_cfg.RETRIEVE_SLOT_2))
    time.sleep(random.uniform(0.3, 0.5))

    print("Restock: closing GE...")
    pyautogui.press("escape")
    time.sleep(random.uniform(0.3, 0.5))

    print("Restock: opening bank...")
    if not open_bank():
        return False

    print("   Depositing all...")
    human_click(*jitter(*cfg.DEPOSIT_BTN))
    time.sleep(0.6)

    # Withdraw the batch the next run_sequence() call needs — it was told
    # to skip its own withdraw since this restock was coming up.
    withdraw_choc()

    print("Restock: closing bank...")
    close_bank()

    print("Restock complete.")
    return True
