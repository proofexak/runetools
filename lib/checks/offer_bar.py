"""
Live check for the GE re-price calibration (lib.ge.offer_progress) — read only, no clicks.

Calibrate first in the overlay's "GE Config" → Re-price: Offer Bar (slot 1), Bar Empty
Colour, Bar Fill Colour, with an offer in progress in GE slot 1. Then, the GE open
on the overview with that offer:

    .venv/bin/python -m lib.checks.offer_bar

Prints how far the offer got every 2 s until Ctrl+C. "no offer bar" while one is
there means the region or a colour is off.
"""
import time


def main():
    import lib.ge as ge
    if not ge._can_follow():
        print("OFFER_BAR / ABORT_BTN aren't calibrated yet — GE Config → Re-price.")
        raise SystemExit(1)
    print(f"Reading OFFER_BAR={ge.cfg.OFFER_BAR} — Ctrl+C to stop.\n")
    try:
        while True:
            done = ge.offer_progress()
            print("no offer bar" if done is None else f"{done:.0%} done")
            time.sleep(2)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
