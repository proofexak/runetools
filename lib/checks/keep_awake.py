"""
Live check for lib/ge.py's keep_awake(): do cursor nudges alone keep the game logged in?

The OSRS Wiki ("Idle") says moving the cursor inside the game window resets the
5-minute logout, even when the window is inactive. This proves it on the real client.

Log in, rest the cursor over the game view, don't touch anything, then run:

    .venv/bin/python -m lib.checks.keep_awake

For 8 minutes it nudges the cursor every next_nudge() seconds and prints each nudge.
Pass: still logged in at the end. Logged out: cursor movement doesn't reset the timer
on this client, and keep_awake() has to go back to key presses.
"""
import time

MINUTES = 8


def main():
    import lib.ge as ge

    print(f"Nudging for {MINUTES} minutes — don't touch the mouse or keyboard. P / Ctrl+C stops.\n")
    start = time.time()
    end = start + MINUTES * 60
    while time.time() < end:
        wait = ge.next_nudge()
        print(f"  next nudge in {wait:5.1f} s")
        time.sleep(min(wait, max(0.0, end - time.time())))
        if time.time() >= end:
            break
        ge.keep_awake()
        print(f"  nudged at {time.time() - start:6.1f} s")
    print("\nDone — are you still logged in?")


if __name__ == "__main__":
    main()
