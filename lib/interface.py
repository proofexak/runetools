"""
Opening and closing in-game interfaces (bank, GE, …) — shared by every bot.

open_interface: find the RuneLite highlight, click it, wait for a pixel that only
shows while the interface is open. wait_for: poll a check with O/P working and a
pause not counted against the timeout.
"""
import time

import pyautogui

import lib.pause as pause
from lib.log import say
from lib.mouse import human_click
from lib.screen import find_color, pixel_matches


def wait_for(check, timeout, poll=0.3):
    """Poll check() until it's true (→ True) or `timeout` seconds pass (→ False).
    O pauses (and restarts the clock), P raises ForceStop. `poll` may be a callable."""
    deadline = time.time() + timeout
    while True:
        if pause.wait():
            deadline = time.time() + timeout
        if check():
            return True
        if time.time() >= deadline:
            return False
        time.sleep(poll() if callable(poll) else poll)


def shows(point_color, tol=15):
    """Check for a calibrated (x, y, (r, g, b)): true while that pixel matches."""
    x, y, rgb = point_color
    return lambda: pixel_matches(x, y, rgb, tol)


def open_interface(rgb, tol, region, check, tries, timeout=5.0, what="interface"):
    """Find the `rgb` highlight in `region`, click it, wait for `check` (x, y, rgb) to
    match. Retries the whole find-click-wait; the last try searches the whole screen."""
    for attempt in range(tries):
        pause.wait()
        pos, _ = find_color(rgb, tol, region=region, whole_screen=attempt == tries - 1)
        if pos:
            human_click(*pos)
            if wait_for(shows(check), timeout):
                return True
            say(f"  {what} did not open (attempt {attempt + 1}/{tries}).")
        else:
            say(f"  {what} not found (attempt {attempt + 1}/{tries}).")
        time.sleep(1.0)
    return False


def close_interface(still_open=None):
    """Escape; if `still_open()` says it didn't take, Escape once more."""
    pyautogui.press("escape")
    time.sleep(0.5)
    if still_open is not None and still_open():
        say("  Interface still open — pressing Escape again.")
        pyautogui.press("escape")
        time.sleep(0.4)
