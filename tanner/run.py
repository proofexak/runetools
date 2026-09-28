"""
Tanner bot session loop.
Called from root run.py after hide type is selected.
"""
import time, random, sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import lib.pause as pause
import lib.log as log
import tanner.config as config
from tanner.tanner import orient_west, walk_to_tanner, trade_ellis, walk_to_bank, do_bank, recover, _wait_stopped
from lib.ge import run_ge_flow

os.makedirs(os.path.join(os.path.dirname(__file__), "log"), exist_ok=True)


def run(stats, start_from_ge=False):
    log.setup(os.path.join(os.path.dirname(__file__), "log", "tanner"))

    print(f"\nHide type: {config.HIDE_TYPE}")
    print("Starting in 3s — switch to OSRS. Press O to pause, P to force-stop.")
    time.sleep(3)

    stats.update({"run": 0, "step": "starting", "start": None, "stop": False})
    pause.reset()
    orient_west()

    if start_from_ge:
        recover()

    run_n = 0
    recovery_charges = [6]
    skip_restock = True
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
            run_n += 1
            stats["run"] = run_n
            print(f"\n{'='*40}\n  RUN {run_n}\n{'='*40}")
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
    print(f"Session ended. Runs: {run_n} | Time: {h:02d}:{m:02d}:{s:02d}")
