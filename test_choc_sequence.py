"""
Standalone test driver for choc/choc.py — bootstraps one withdrawal, then
runs a single grind/deposit/withdraw sequence. Doesn't exercise the GE
restock flow (restock_ge()) — that needs its own separately calibrated
fields (GE Region, Sell Slot, Buy Button, etc.) in the config editor.

Calibrate first via choc/config_editor.py's fields (Bank Booth Region, Bank
Check, Chocolate Bank Slot, Deposit Button, Inventory Check, Knife Slot,
Chocolate Inv Slot), then run this standing near a bank booth — already
switched to the chocolate tab — with a knife already in your inventory's
last slot:

    .venv/bin/python test_choc_sequence.py
"""
import time

import choc.config as cfg
from choc.choc import run_sequence, bootstrap_withdraw


def _flatten(val):
    if isinstance(val, (tuple, list)):
        for item in val:
            yield from _flatten(item)
    else:
        yield val


def _is_unset(val):
    """True if val is still a zeroed template default — flattens nested
    tuples (point_color is (x, y, (r, g, b))) and checks every value is 0."""
    return all(x == 0 for x in _flatten(val))


if __name__ == "__main__":
    unset = [name for name, val in [
        ("BANK_BOOTH_REGION", cfg.BANK_BOOTH_REGION),
        ("BANK_CHECK", cfg.BANK_CHECK),
        ("CHOC_BANK_SLOT", cfg.CHOC_BANK_SLOT),
        ("DEPOSIT_BTN", cfg.DEPOSIT_BTN),
        ("INVENTORY_CHECK", cfg.INVENTORY_CHECK),
        ("KNIFE_SLOT", cfg.KNIFE_SLOT),
        ("CHOC_INV_SLOT", cfg.CHOC_INV_SLOT),
    ] if _is_unset(val)]
    if unset:
        print(f"Not calibrated yet: {', '.join(unset)} — set these in the "
              "overlay's 'Chocolate Config' menu first.")
        raise SystemExit(1)

    print("Starting in 3s — switch to OSRS...")
    time.sleep(3)

    if bootstrap_withdraw():
        run_sequence()
