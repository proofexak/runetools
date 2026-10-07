"""
Live check for the restock trigger (PRO-100): reads HIDE_COUNT_REGION once a second and
prints whether the hide stack shows a count. Calibrate "Hide Count Region" in the tanner
editor first (Bank section: a box over the digits on the hide stack, not the icon), open
the bank on the hide tab, then:

    .venv/bin/python -m tanner.checks.hide_count

"number shown" = 2 or more hides; "last 1 -> restock" = no count (the bot would restock).
Ctrl+C to stop.
"""
import time


def main():
    import tanner.actions as actions
    if actions.hide_count_shown() is None:
        print("HIDE_COUNT_REGION isn't calibrated yet — tanner editor → Bank → Hide Count Region.")
        raise SystemExit(1)
    print(f"Reading HIDE_COUNT_REGION={actions.HIDE_COUNT_REGION} — Ctrl+C to stop.\n")
    try:
        while True:
            print("number shown" if actions.hide_count_shown() else "last 1 -> restock")
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
