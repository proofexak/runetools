"""
Crafting bot actions — shift + alt orb combo crafting cycle.
Imports config from config.py and shared utilities from lib/.
"""
import time, random, sys, os
import pyautogui

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib.mouse  import human_move, jitter, release_key
from lib.screen import pixel_matches, get_pixel_color
import lib.pause as pause

import crafting.config as config


def _wait(seconds, spread=0.2):
    """Sleep for `seconds` ± spread*100% — human timing has no fixed durations."""
    time.sleep(random.uniform(seconds * (1 - spread), seconds * (1 + spread)))


# Settle time after keyDown() before the click that depends on it. Streamed
# setups (e.g. GeForce NOW) add real network round-trip on top of local input
# lag, so a click sent too soon after keyDown can reach the remote session
# before the modifier key is registered there — this needs to be generous,
# not the ~0.1s that's fine for a locally-running game.
_MODIFIER_SETTLE = 0.35


def _click_in_place(with_alt=False):
    """Click at the current cursor position (already on the click point).
    with_alt taps alt down/up around just this one click, shift stays held by the caller."""
    time.sleep(random.uniform(0.03, 0.08))
    if with_alt:
        pyautogui.keyDown("alt")
        try:
            _wait(_MODIFIER_SETTLE)
            pyautogui.click()
        finally:
            pyautogui.keyUp("alt")
    else:
        pyautogui.click()


def check_done(point):
    x, y = point
    actual = get_pixel_color(x, y)
    matched = pixel_matches(x, y, config.DONE_CHECK_COLOR, tol=config.DONE_TOL)
    print(f"  [done-check] point=({x},{y}) actual={actual} expected={config.DONE_CHECK_COLOR} "
          f"tol={config.DONE_TOL} match={matched}")
    return matched


def log_all_done_checks():
    """Diagnostic: print the done-check result for every configured item,
    without clicking anything — useful for verifying calibration."""
    if not config.ITEMS:
        print("No items configured.")
        return
    for i, item in enumerate(config.ITEMS, start=1):
        tag = " (skipped)" if item.get("skip") else ""
        print(f"-- Item {i}{tag} --")
        check_done(item["done_point"])


def _switch_tab(point):
    _wait(0.5)
    human_move(*point)
    _wait(0.2)
    pyautogui.click()


def grab_currency():
    """
    One-time session setup (steps 1-2): switch to the currency tab, hold
    shift, right-click the orb, then switch to the crafting tab. Leaves shift
    held and the currency on the cursor for every item — call release() once
    the whole session is done (or on error/stop).
    """
    # 0. Switch to the currency stash tab.
    _switch_tab(config.CURRENCY_STASH_TAB)

    # 1. Move to alt orb after 2s.
    _wait(2.0)
    human_move(*jitter(*config.ALT_ORB, n=3))

    # 2. Hold shift, right-click after 0.5s.
    _wait(0.5)
    pyautogui.keyDown("shift")
    _wait(_MODIFIER_SETTLE)
    pyautogui.rightClick()

    # Switch to the crafting stash tab (still holding shift + orb on cursor).
    _switch_tab(config.CRAFTING_STASH_TAB)


def release():
    """Release shift at the end of the session (or on error/stop)."""
    release_key("shift")


def craft_item(item):
    """
    Crafts a single item (steps 3-8), retrying until its done-check matches —
    does not give up. Assumes grab_currency() has already run (shift held,
    currency on cursor, crafting tab open). `item` is one entry of
    config.ITEMS: {"click_point": (x, y), "done_point": (x, y)}.
    """
    pause.wait()

    # 3. Move to click point after 0.5s (shift still held).
    _wait(0.5)
    human_move(*item["click_point"])

    # 4. Left click after 0.5s.
    _wait(0.5)
    pyautogui.click()

    # Settle time for the craft + video round-trip before checking.
    _wait(1.0)

    # 5. Check done point after 0.2s.
    _wait(0.2)
    if check_done(item["done_point"]):
        return True

    # 6-8. Retry, alternating alt-click / plain-click, checking after each,
    # until a match — no give-up limit.
    use_alt = True
    while True:
        pause.wait()
        _wait(0.2)
        _click_in_place(with_alt=use_alt)
        use_alt = not use_alt

        _wait(0.2)
        if check_done(item["done_point"]):
            return True
