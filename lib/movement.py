"""
Movement detection — poll a screen region for pixel changes to detect when
the character stops walking.
"""
import time

import lib.pause as pause
import lib.vision as vision
from lib.screen import grab


class Stillness:
    """Counts consecutive calm frames: update(diff) returns True once `stable_count`
    frames in a row have diff <= thresh; any frame above thresh resets the count."""

    def __init__(self, thresh, stable_count):
        self.thresh, self.stable_count, self.stable = thresh, stable_count, 0

    def update(self, diff):
        self.stable = 0 if diff > self.thresh else self.stable + 1
        return self.stable >= self.stable_count


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
    time.sleep(0.8)
    deadline = time.time() + timeout
    still = Stillness(thresh, stable_count)
    prev, _ = grab(region, absolute=True)
    while time.time() < deadline:
        if paused_fn:
            paused_fn()
        time.sleep(poll)
        curr, _ = grab(region, absolute=True)
        diff = vision.frame_difference(curr, prev)
        if still.update(diff):
            print("  Stopped.              ")
            return True
        if diff > thresh:
            print(f"  [walking] diff={diff:.1f}", end="\r")
        prev = curr
    print("  Walk timeout.")
    return False
