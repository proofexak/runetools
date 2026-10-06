"""
Run-energy reading and stamina-potion drinking.
Calibrate via the overlay's "Energy Config" menu + calibrate_energy_digits.py
before relying on this (see those tools' docstrings).
"""
import time, random
import pyautogui

from lib.mouse import human_click, jitter
from lib.screen import find_color, pixel_matches
import lib.energy_config as cfg
from lib.digit_templates import read_number, load_templates

MAGENTA     = (255, 0, 255)
MAGENTA_TOL = 10

_templates = None


def _templates_cached():
    global _templates
    if _templates is None:
        _templates = load_templates()
    return _templates


def read_energy():
    """Current run-energy percentage (0-100), or None if unreadable."""
    _, value = read_number(cfg.ENERGY_REGION, _templates_cached())
    return value


def needs_stamina(energy, threshold, force=False, if_unreadable=False):
    """Should we drink? force always does; an unreadable reading (None) answers
    `if_unreadable`; otherwise drink below threshold."""
    if force:
        return True
    if energy is None:
        return if_unreadable
    return energy < threshold


def drink_stamina():
    """Drink the whole bottle (all 4 doses) from the stamina potion slot.
    The potion stays in the same slot as doses are consumed, so this is 4
    clicks on the same spot with a short pause between each."""
    for _ in range(4):
        x, y = jitter(*cfg.STAMINA_POTION_SLOT)
        human_click(x, y)
        time.sleep(1.3)


def maybe_drink_stamina(threshold=None):
    """Drink a stamina potion if energy is below threshold (defaults to
    cfg.DRINK_THRESHOLD). Returns True if a potion was drunk."""
    if threshold is None:
        threshold = cfg.DRINK_THRESHOLD
    if needs_stamina(read_energy(), threshold):
        drink_stamina()
        return True
    return False


BANK_CLOSED = "bank_closed"


def restock_stamina_at_bank(force=False, bank_open=None):
    """
    Full sequence to run while standing at an *already open* bank: check
    energy, and if below DRINK_THRESHOLD, withdraw + drink a stamina
    potion, then reopen the bank and deposit everything again.

    The caller is responsible for detecting/opening the bank before calling
    this and for whatever it wants to do after (e.g. re-withdrawing
    materials) — this only handles the stamina potion side trip.

    Returns True if a potion was withdrawn + drunk, False if energy was
    fine (or force=False and above threshold) or the booth couldn't be
    found again afterwards.

    bank_open: the caller's "is the bank interface open?" check (waits a few
    seconds). Given, the bank must really reopen after the drink before the
    deposit click — one more booth click if it didn't — and a drink after
    which it can't be reopened returns BANK_CLOSED instead, so the caller
    doesn't go on clicking bank buttons on the game world (the potion would
    stay in the inventory and no materials would be withdrawn).
    """
    # Unlike maybe_drink_stamina, an unreadable energy value drinks here —
    # we're already at the bank, so topping up is the safe side.
    if not needs_stamina(read_energy(), cfg.DRINK_THRESHOLD, force=force, if_unreadable=True):
        return False

    human_click(*jitter(*cfg.POTION_TAB))
    time.sleep(0.6)

    human_click(*jitter(*cfg.BANK_SLOT_1))
    time.sleep(0.6)

    pyautogui.press("escape")
    time.sleep(random.uniform(0.4, 0.6))

    ix, iy, icolor = cfg.INVENTORY_CHECK
    if not pixel_matches(ix, iy, icolor):
        pyautogui.press("escape")
        time.sleep(0.4)

    drink_stamina()
    time.sleep(0.6)

    if bank_open is not None:
        return BANK_CLOSED if not _reopen_bank(bank_open) else _deposit()

    pos, _ = find_color(MAGENTA, MAGENTA_TOL, outside_pad=0,
                         region=cfg.BANK_BOOTH_REGION, whole_screen=True)   # the only try
    if not pos:
        return False
    bx, by = pos
    human_click(bx, by)
    time.sleep(1.0)

    human_click(*jitter(*cfg.DEPOSIT_BTN))
    return True


def _reopen_bank(bank_open, tries=2):
    """Click the booth until bank_open() confirms the interface (`tries` clicks)."""
    for attempt in range(tries):
        pos, _ = find_color(MAGENTA, MAGENTA_TOL, outside_pad=0,
                            region=cfg.BANK_BOOTH_REGION, whole_screen=True)
        if not pos:
            print("  [STAMINA] Booth not found to reopen the bank.")
            return False
        human_click(*pos)
        if bank_open():
            return True
        print(f"  [STAMINA] Bank didn't reopen after the potion (click {attempt + 1}/{tries}).")
    return False


def _deposit():
    human_click(*jitter(*cfg.DEPOSIT_BTN))
    return True
