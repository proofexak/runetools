"""
Chocolate dust grinding — withdraw/grind/deposit loop, plus a GE restock
(sell accumulated dust, buy more bars) run periodically from choc/run.py.
"""
import time, random
import pyautogui

import lib.pause as pause
import lib.ge as ge
from lib.interface import open_interface
from lib.mouse import human_click, jitter, quick_click
from lib.restock import Restock
from lib.screen import pixel_matches
import choc.config as cfg


def open_bank():
    """Find + click the blue banker/booth, confirm it opened. Skips the
    find+click entirely if the bank's already open. Retries the whole
    find-click-confirm cycle a few times — the booth can be briefly
    obscured or the bank slow to open, which is what killed batch 2 in
    testing (single attempt, gave up immediately)."""
    bx, by, expected = cfg.BANK_CHECK
    if pixel_matches(bx, by, expected):
        return True
    return open_interface(cfg.BLUE, cfg.BLUE_TOL, cfg.BANK_BOOTH_REGION, cfg.BANK_CHECK,
                          cfg.BANK_OPEN_RETRIES, cfg.BANK_OPEN_TIMEOUT, what="   Bank")


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
        pause.wait()                               # O pauses between bars, P stops
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


def restock_ge(quantity):
    """Sell accumulated chocolate dust and buy `quantity` more chocolate
    bars at the GE, then bank the bars. No teleport/orient — the grind spot
    is already within reach of both the bank and the GE. `quantity` is the
    bar count the session started with, so restocking always brings the
    bank back up to that same starting amount. (True, None) or (False, reason)."""
    restock = Restock.from_config(cfg, "chocolate bar", quantity)

    print("Restock: opening bank...")
    if not open_bank():
        return False, "could not open the bank"

    print("   Switching to chocolate tab...")
    human_click(*jitter(*cfg.CHOCOLATE_TAB))
    time.sleep(random.uniform(0.3, 0.5))

    print("   Withdrawing dust (noted)...")
    if not ge.withdraw_noted(cfg.DUST_BANK_SLOT):
        return False, "notes toggle didn't respond"

    print("Restock: closing bank...")
    close_bank()

    print("Restock: opening GE...")
    if not ge.open_ge():
        return False, "could not open the GE"
    ok, why = ge.trade(restock)
    if not ok:
        return False, why

    print("Restock: closing GE...")
    ge.close_ge()

    print("Restock: opening bank...")
    if not open_bank():
        return False, "could not open the bank after the GE"

    print("   Depositing all...")
    human_click(*jitter(*cfg.DEPOSIT_BTN))
    time.sleep(0.6)

    # Withdraw the batch the next run_sequence() call needs — it was told
    # to skip its own withdraw since this restock was coming up.
    withdraw_choc()

    print("Restock: closing bank...")
    close_bank()

    print("Restock complete.")
    return True, None
