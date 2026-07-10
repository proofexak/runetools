"""
Standalone test: does clicking STAMINA_POTION_SLOT actually drink a stamina
potion and restore energy?

Calibrate first (overlay's "Energy Config" menu):
  - ENERGY_REGION        (already needed for lib/energy.py)
  - STAMINA_POTION_SLOT   inventory slot holding a stamina potion
  - DRINK_THRESHOLD       drink when energy is below this %

Have your inventory open with a stamina potion actually in that slot, then:

    .venv/bin/python test_drink_stamina.py

Reads energy, prints it, drinks one dose, then re-reads energy a few times
to confirm it went up.
"""
import time

import lib.energy_config as cfg
from lib.energy import read_energy, drink_stamina

if __name__ == "__main__":
    if cfg.STAMINA_POTION_SLOT == (0, 0):
        print("STAMINA_POTION_SLOT isn't calibrated yet — open the overlay's "
              "'Energy Config' menu and capture it first.")
        raise SystemExit(1)

    before = read_energy()
    print(f"Energy before: {before}")

    print(f"Drinking from STAMINA_POTION_SLOT={cfg.STAMINA_POTION_SLOT} ...")
    drink_stamina()

    print("Watching energy for 5s after drinking:")
    for _ in range(5):
        time.sleep(1)
        print(f"  energy={read_energy()}")

    after = read_energy()
    if before is not None and after is not None and after > before:
        print(f"\nLooks correct — energy went {before} -> {after}.")
    else:
        print(f"\nNo clear increase ({before} -> {after}) — check "
              "STAMINA_POTION_SLOT is right and a potion is actually in that slot.")
