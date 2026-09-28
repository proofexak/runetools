"""
Movement detection — poll a screen region for pixel changes to detect when
the character stops walking.
"""
import time
import numpy as np
import mss

import lib.pause as pause


def wait_until_stopped(region, thresh=3.0, stable_count=3, poll=0.15,
                        timeout=20.0, paused_fn=pause.wait):
    """
    Block until the game view stops changing (character stopped walking).
    region      — (left, top, width, height) area to watch
    thresh      — mean pixel diff below which movement is considered stopped
    stable_count — how many consecutive stable polls required
    poll        — seconds between polls
    timeout     — give up after this many seconds
    paused_fn   — no-arg callable that blocks while paused (default: the O/P pause gate)
    Returns True if stopped cleanly, False on timeout.
    """
    def _grab():
        with mss.mss() as sct:
            shot = sct.grab({"left": region[0], "top": region[1],
                             "width": region[2], "height": region[3]})
        return np.array(shot)[:, :, :3].mean(axis=2).astype(float)

    time.sleep(0.8)
    deadline = time.time() + timeout
    stable, prev = 0, _grab()
    while time.time() < deadline:
        if paused_fn:
            paused_fn()
        time.sleep(poll)
        curr = _grab()
        diff = np.abs(curr - prev).mean()
        if diff > thresh:
            stable = 0
            print(f"  [walking] diff={diff:.1f}", end="\r")
        else:
            stable += 1
            if stable >= stable_count:
                print("  Stopped.              ")
                return True
        prev = curr
    print("  Walk timeout.")
    return False
