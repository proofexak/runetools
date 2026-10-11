"""
Chocolate dust grinding — withdraw/grind/deposit loop, plus a GE restock
(sell accumulated dust, buy more bars) when a bank visit sees the bars are out.
"""
import time, random
import pyautogui

import lib.pause as pause
import lib.ge as ge
from lib.interface import open_interface
from lib.mouse import human_click, human_move, human_press, jitter, quick_click
from lib.restock import Restock
from lib.screen import pixel_matches, grab
import lib.vision as vision
import lib.human as human
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
    human_press("escape")
    human.sleep(0.5, 0.75)

    ix, iy, icolor = cfg.INVENTORY_CHECK
    if pixel_matches(ix, iy, icolor):
        return
    print("   Inventory not open — pressing Escape again.")
    human_press("escape")
    human.sleep(0.4, 0.65)


# ── When to restock: read off the bank, like tanner ──────────────────────────

def _count_region():
    return tuple(getattr(cfg, "CHOC_COUNT_REGION", (0, 0, 0, 0)))


def bar_count_calibrated():
    _, _, w, h = _count_region()
    return w > 0 and h > 0


def bar_slot_calibrated():
    x, y, _ = getattr(cfg, "EMPTY_SLOT_BG", (0, 0, (0, 0, 0)))
    return (x, y) != (0, 0)


def bar_slot_filled():
    """Bank open, right after the withdraw: does slot 27 (CHOC_INV_SLOT, next to the knife)
    hold a bar? Withdraw-All fills from slot 1, so a batch under 27 bars leaves it empty —
    and the grind would put the knife on nothing, deposit, see the count, withdraw … forever.
    None while EMPTY_SLOT_BG isn't calibrated."""
    if not bar_slot_calibrated():
        return None
    _, _, bg = cfg.EMPTY_SLOT_BG
    cx, cy = cfg.CHOC_INV_SLOT
    # One read, once the withdraw has landed: it shows a game tick (0.6 s) + lag after the
    # click, and withdraw_choc() only waits 0.6 s — read then, a full 27 looked empty.
    human.sleep(0.6, 0.9)
    frame, _ = grab((cx - 10, cy - 10, 20, 20))
    return vision.filled_slot_count(frame, [(10, 10)], bg, getattr(cfg, "EMPTY_SLOT_TOL", 20)) == 1


def dust_count_region():
    """Where the dust stack's (DUST_BANK_SLOT) count is drawn: CHOC_COUNT_REGION moved by the
    step from the bar slot to the dust slot (tanner's leather box works the same way). None
    while the bar count isn't calibrated — then the restock always sells."""
    if not bar_count_calibrated():
        return None
    x, y, w, h = _count_region()
    dx, dy = cfg.DUST_BANK_SLOT[0] - cfg.CHOC_BANK_SLOT[0], cfg.DUST_BANK_SLOT[1] - cfg.CHOC_BANK_SLOT[1]
    return (x + dx, y + dy, w, h)


def withdraw_or_restock():
    """Bank open: chocolate tab → does the bar stack show a count? A count → withdraw the
    next batch and close (True); none (1 or 0 left), or a batch too short to reach slot 27
    (deposited back) → "restock", the bank left open for the GE trip (run_ge_flow(bank_open=True)). The mouse rests on Deposit for the read: the tab's
    "View tab" tooltip would cover the count box and its white text read as a count."""
    print("   Switching to chocolate tab...")
    human_click(*jitter(*cfg.CHOCOLATE_TAB))
    human_move(*jitter(*cfg.DEPOSIT_BTN, n=3))
    human.sleep(0.4, 0.6)
    if ge.stack_shown(_count_region()) is False:
        print("   No count on the chocolate bars — restocking...")
        return "restock"
    withdraw_choc()
    if bar_slot_filled() is False:
        print("   Fewer than a full batch (slot 27 empty) — depositing them, restocking...")
        human_click(*jitter(*cfg.DEPOSIT_BTN))
        time.sleep(0.6)
        return "restock"
    print("Closing bank...")
    close_bank()
    return True


def bootstrap_withdraw():
    """Called once at session start: open the bank, then withdraw_or_restock(). Every later
    withdrawal piggybacks on that batch's deposit inside run_sequence(), so the booth is
    only ever clicked once per bank visit — never once to withdraw and again to deposit.
    True, "restock" (no bars to start with), or False (no bank)."""
    print("Opening bank...")
    if not open_bank():
        return False
    return withdraw_or_restock()


INVENTORY_TRIES = 2


def ensure_inventory():
    """Before grinding: the inventory must be the open side panel, or every grind click lands
    on whatever panel is showing (2026-10-11, after a restock's bank closed). INVENTORY_CHECK
    is a pixel of the backpack tab's red "selected" highlight, so it's also the button to
    click. False when it won't open; uncalibrated (0, 0): not checked."""
    ix, iy, icolor = cfg.INVENTORY_CHECK
    if (ix, iy) == (0, 0) or pixel_matches(ix, iy, icolor):
        return True
    for _ in range(INVENTORY_TRIES):
        print("   Inventory not open — clicking its tab...")
        human_click(*jitter(ix, iy, n=3))
        human.sleep(0.4, 0.6)
        if pixel_matches(ix, iy, icolor):
            return True
    return False


def run_sequence():
    """Grind, then a single bank visit: deposit the dust, then withdraw_or_restock().
    True, "restock" (the bars ran out — the bank is left open), or False (no bank, or the
    inventory won't open — never grinds blind)."""
    if not ensure_inventory():
        print("   Inventory didn't open — not grinding blind.")
        return False
    print(f"Grinding chocolate x{cfg.GRIND_COUNT}...")
    for i in range(cfg.GRIND_COUNT):
        pause.wait()                               # O pauses between bars, P stops
        quick_click(*cfg.KNIFE_SLOT)
        human.sleep(0.07, 0.1125)
        quick_click(*cfg.CHOC_INV_SLOT)
        human.sleep(0.127, 0.183)
        print(f"   {i + 1}/{cfg.GRIND_COUNT}")

    print("Opening bank...")
    if not open_bank():
        return False

    print("   Depositing dust...")
    human_click(*jitter(*cfg.DEPOSIT_BTN))
    time.sleep(0.6)

    result = withdraw_or_restock()
    if result is True:
        print("Sequence complete.")
    return result


def restock_ge(quantity):
    """Sell the accumulated chocolate dust and buy `quantity` more chocolate bars: tanner's
    GE trip (lib.ge.run_ge_flow) without the teleport — the grind spot is at the GE — in the
    bank the visit that saw no count left open. The price is checked before anything moves,
    and no count on the dust stack (dust_count_region()) means nothing to sell: buy only. The
    bank visit after the GE deposits all, then withdraws the next batch. `quantity` is the
    count asked at launch. (True, None) or (False, reason)."""
    restock = Restock.from_config(cfg, "chocolate bar", quantity, sell_item="chocolate dust",
                                  sell_inv_slot=cfg.SELL_INV_SLOT, bank_tab=cfg.CHOCOLATE_TAB,
                                  sell_slot=cfg.DUST_BANK_SLOT, deposit_btn=cfg.DEPOSIT_BTN,
                                  sell_count_region=dust_count_region(),
                                  withdraw_slot=cfg.CHOC_BANK_SLOT)
    return ge.run_ge_flow(restock, teleport=False, bank_open=True)
