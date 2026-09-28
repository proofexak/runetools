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
    energy = read_energy()
    if energy is not None and energy < threshold:
        drink_stamina()
        return True
    return False


def restock_stamina_at_bank(force=False):
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
    """
    energy = read_energy()
    if not force and energy is not None and energy >= cfg.DRINK_THRESHOLD:
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

    pos, _ = find_color(MAGENTA, MAGENTA_TOL, outside_pad=0,
                         region=cfg.BANK_BOOTH_REGION)
    if not pos:
        return False
    bx, by = pos
    human_click(bx, by)
    time.sleep(1.0)

    human_click(*jitter(*cfg.DEPOSIT_BTN))
    return True
