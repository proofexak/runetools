"""
Standalone test driver for lib/energy.py's restock_stamina_at_bank().

Run this while standing at the bank with it already open (the caller in the
real bot will handle detecting/opening it — this assumes it's already open).

    .venv/bin/python -m lib.checks.drink_sequence

Pass --force to run the sequence regardless of current energy (useful for
testing the mechanics without needing to actually be low on energy).
"""
import sys, time

import lib.energy_config as cfg
from lib.energy import restock_stamina_at_bank

if __name__ == "__main__":
    unset = [name for name, val in [
        ("POTION_TAB", cfg.POTION_TAB),
        ("BANK_SLOT_1", cfg.BANK_SLOT_1),
        ("INVENTORY_CHECK", cfg.INVENTORY_CHECK),
        ("STAMINA_POTION_SLOT", cfg.STAMINA_POTION_SLOT),
        ("BANK_BOOTH_REGION", cfg.BANK_BOOTH_REGION),
        ("DEPOSIT_BTN", cfg.DEPOSIT_BTN),
    ] if not any(val)]
    if unset:
        print(f"Not calibrated yet: {', '.join(unset)} — set these in the "
              "overlay's 'Energy Config' menu first.")
        raise SystemExit(1)

    print("Starting in 3s — switch to OSRS...")
    time.sleep(3)

    result = restock_stamina_at_bank(force="--force" in sys.argv)
    print(f"Drunk: {result}")
