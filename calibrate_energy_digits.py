"""
Builds digit templates for lib/digit_templates.py by watching your real
run-energy readout and asking you to confirm what it currently shows.

Needs ENERGY_REGION calibrated first (overlay's "Energy Config" menu).
Run this while playing normally — energy naturally cycles through most
digits (both tens and units place) as it drains from 100 to 0. It tells you
which digits (0-9) are still missing a template after each capture.

    .venv/bin/python calibrate_energy_digits.py
"""
import mss
from PIL import Image

import lib.energy_config as cfg
from lib.digit_templates import preprocess, segment_glyphs, save_template, TEMPLATE_DIR

ALL_DIGITS = set("0123456789")


def capture_glyphs():
    l, t, w, h = cfg.ENERGY_REGION
    pad = 6
    l -= pad;  t -= pad;  w += pad * 2;  h += pad * 2
    with mss.mss() as sct:
        shot = sct.grab({"left": l, "top": t, "width": w, "height": h})
    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    bw = preprocess(img)
    return segment_glyphs(bw)


def have_digits():
    import os
    if not os.path.isdir(TEMPLATE_DIR):
        return set()
    return {f[:-4] for f in os.listdir(TEMPLATE_DIR) if f.endswith(".png")}


if __name__ == "__main__":
    if cfg.ENERGY_REGION == (0, 0, 0, 0):
        print("ENERGY_REGION isn't calibrated yet — open the overlay's "
              "'Energy Config' menu and capture it first.")
        raise SystemExit(1)

    print("Digit calibration — type the number your energy currently shows "
          "in-game after each capture, or press Enter to skip/recapture, "
          "or 'q' to stop.\n")

    while True:
        missing = ALL_DIGITS - have_digits()
        if not missing:
            print("All 10 digits captured. Done!")
            break
        print(f"Still need: {''.join(sorted(missing))}")

        glyphs = capture_glyphs()
        print(f"Captured {len(glyphs)} glyph(s).")
        answer = input("What number is that? ").strip()

        if answer.lower() == "q":
            break
        if not answer:
            continue
        if not answer.isdigit():
            print("  (not a plain number, ignoring)")
            continue
        if len(answer) != len(glyphs):
            print(f"  ({len(answer)} digits typed but {len(glyphs)} glyph(s) "
                  f"segmented — mismatch, skipping this capture)")
            continue

        for ch, glyph in zip(answer, glyphs):
            save_template(ch, glyph)
        print(f"  saved: {answer}\n")
