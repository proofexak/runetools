"""
Standalone test driver for lib/energy.py's read_energy().

Calibrate first:
  1. Overlay's "Energy Config" menu -> capture ENERGY_REGION.
  2. .venv/bin/python calibrate_energy_digits.py  (builds digit templates —
     OCR/Tesseract proved unreliable on this font; template matching is
     what actually works.)

Then run this with RuneLite visible:

    .venv/bin/python test_energy.py

Prints the parsed percentage every second until Ctrl+C.
"""
import time

import lib.energy_config as cfg
from lib.digit_templates import TEMPLATE_DIR
from lib.energy import read_energy, _templates_cached

if __name__ == "__main__":
    if cfg.ENERGY_REGION == (0, 0, 0, 0):
        print("ENERGY_REGION isn't calibrated yet — open the overlay's "
              "'Energy Config' menu and capture it first.")
        raise SystemExit(1)

    templates = _templates_cached()
    if not templates:
        print(f"No digit templates found in {TEMPLATE_DIR} — run "
              "calibrate_energy_digits.py first.")
        raise SystemExit(1)
    print(f"Loaded {len(templates)} digit template(s): "
          f"{''.join(sorted(templates))}\n")

    print(f"Reading ENERGY_REGION={cfg.ENERGY_REGION} — Ctrl+C to stop.\n")
    try:
        while True:
            print(f"energy={read_energy()}")
            time.sleep(1)
    except KeyboardInterrupt:
        pass
