"""
Al Kharid tanner bot — entry point.
Stand at the bank before running. Press P to pause/resume, Ctrl+C to stop.
Run find_tanner.py to calibrate positions.
"""
import time, random, sys, threading, os, argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import lib.pause as pause
import lib.log as log
import lib.overlay as overlay
from lib.overlay import start as start_overlay
import tanner.config as config
from tanner.tanner import orient_west, walk_to_tanner, trade_ellis, walk_to_bank, do_bank, recover, _wait_stopped
from tanner.config_editor import open_editor
from lib.ge import run_ge_flow
from lib.ge_config_editor import open_ge_editor

# ── Setup ─────────────────────────────────────────────────────────────────────

os.makedirs(os.path.join(os.path.dirname(__file__), "log"), exist_ok=True)
log.setup(os.path.join(os.path.dirname(__file__), "log", "tanner"))
pause.setup("p")

_ap = argparse.ArgumentParser()
_ap.add_argument("--select", action="store_true")
_use_selector = _ap.parse_known_args()[0].select

# ── Overlay ───────────────────────────────────────────────────────────────────

stats = {"run": 0, "step": "starting", "start": None, "stop": False}
_hide_selected  = threading.Event()
_start_from_ge  = [False]

if not _use_selector:
    _hide_selected.set()

def _select_from_ge(value):
    config.HIDE_TYPE = value
    _start_from_ge[0] = True
    _hide_selected.set()

def _ge_btn(value):
    return ("GE", lambda v=value: _select_from_ge(v))

MENU = [
    ("Tanning", [
        ("Green Dragonhide", "green dragonhide", "#1a4a1a", "#2d7a2d", _ge_btn("green dragonhide")),
        ("Blue Dragonhide",  "blue dragonhide",  "#0d2444", "#1a4a88", _ge_btn("blue dragonhide")),
        ("Red Dragonhide",   "red dragonhide",   "#440d0d", "#882020", _ge_btn("red dragonhide")),
        ("Black Dragonhide", "black dragonhide", "#1a1a1a", "#333333", _ge_btn("black dragonhide")),
        ("⚙ Configure",      open_editor,        "#1a1a33", "#2a2a55"),
    ], "#1a3a1a", "#2d6a2d"),
    ("⚙ GE Config", open_ge_editor, "#1a1a33", "#2a2a55"),
    ("Exit", lambda: __import__('os')._exit(0), "#550000", "#881111"),
]

def _on_select(value):
    config.HIDE_TYPE = value

start_overlay(
    stats         = stats,
    hide_selected = _hide_selected,
    use_selector  = _use_selector,
    menu          = MENU,
    on_select     = _on_select,
    stats_extra   = lambda s: f"Hides:   {s['run'] * 27}",
)

# ── Session loop ──────────────────────────────────────────────────────────────

while True:
    _hide_selected.wait()
    print(f"\nHide type: {config.HIDE_TYPE}")
    print("Starting in 3s — switch to OSRS. Press P to pause.")
    time.sleep(3)

    stats.update({"run": 0, "step": "starting", "start": None, "stop": False})
    pause.reset()
    orient_west()
    if _start_from_ge[0]:
        _start_from_ge[0] = False
        recover()

    run = 0
    recovery_charges = [6]
    skip_restock = True   # skip on first bank run of session
    start_time = time.time()
    stats["start"] = start_time

    def _try_recover(reason):
        print(f"\n[RECOVERY] Triggered: {reason}")
        if recovery_charges[0] <= 0:
            print("[RECOVERY] No charges remaining — stopping.")
            return False
        print(f"[RECOVERY] Using charge ({recovery_charges[0]} remaining)...")
        recovery_charges[0] -= 1
        return recover()

    try:
        while True:
            run += 1
            stats["run"] = run
            print(f"\n{'='*40}\n  RUN {run}\n{'='*40}")
            pause.wait()

            if stats["stop"]:
                print("Stop requested via overlay.")
                break

            stats["step"] = "walk → tanner"
            if not walk_to_tanner():
                result = _try_recover("walk_to_tanner failed")
                if result == "done":
                    stats["step"] = "done"
                    print("\nAll hides tanned. Session complete.")
                    break
                if not result:
                    break
                continue

            stats["step"] = "trading ellis"
            if not trade_ellis():
                result = _try_recover("trade_ellis failed")
                if result == "done":
                    stats["step"] = "done"
                    print("\nAll hides tanned. Session complete.")
                    break
                if not result:
                    break
                continue

            stats["step"] = "tanning..."
            _wait_stopped()

            stats["step"] = "walk → bank"
            if not walk_to_bank():
                result = _try_recover("walk_to_bank failed")
                if result == "done":
                    stats["step"] = "done"
                    print("\nAll hides tanned. Session complete.")
                    break
                if not result:
                    break
                continue

            stats["step"] = "banking"
            result = do_bank(skip_restock_check=skip_restock)
            skip_restock = False
            if result == "restock":
                if not config.RESTOCK_GE:
                    print("\n[DONE] Hides depleted and restock disabled — stopping.")
                    break
                stats["step"] = "restocking"
                print("\n[RESTOCK] Bank slot 2 empty — heading to GE...")
                if not run_ge_flow(config.HIDE_TYPE, recover):
                    break
                skip_restock = True
                continue
            if not result:
                result = _try_recover("do_bank failed")
                if not result:
                    break
                skip_restock = True
                continue

            time.sleep(random.uniform(0.5, 1.2))

    except pause.ForceStop:
        print("Force stopped via overlay.")

    elapsed = time.time() - start_time
    h, rem = divmod(int(elapsed), 3600)
    m, s   = divmod(rem, 60)
    print(f"Session ended. Runs: {run} | Time: {h:02d}:{m:02d}:{s:02d}")

    _hide_selected = threading.Event()
    overlay.show_selector(_hide_selected)
