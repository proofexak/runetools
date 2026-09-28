"""
Chocolate dust bot session loop.
Called from root run.py after the starting chocolate count is entered.
"""
import time, random, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import lib.pause as pause
import lib.log as log
import choc.config as config
from choc.choc import run_sequence, bootstrap_withdraw, restock_ge

os.makedirs(os.path.join(os.path.dirname(__file__), "log"), exist_ok=True)


def run(stats, start_count):
    log.setup(os.path.join(os.path.dirname(__file__), "log", "choc"))

    print(f"\nStarting chocolate: {start_count}")
    print("Starting in 3s — switch to OSRS. Press O to pause, P to force-stop.")
    time.sleep(3)

    stats.update({"run": 0, "step": "starting", "start": None, "stop": False})
    pause.reset()

    stats["step"] = "withdrawing"
    if not bootstrap_withdraw():
        print("Could not withdraw starting chocolate — aborting.")
        return

    remaining  = start_count
    run_n      = 0
    start_time = time.time()
    stats["start"] = start_time

    # Runs indefinitely — once `remaining` (the starting bar count) is
    # ground through, restock buys `start_count` more at the GE and
    # `remaining` resets, so there's no bar count to run out of. Only stops
    # via the overlay's pause/stop controls or a failed bank/GE step.
    try:
        while True:
            run_n += 1
            stats["run"]  = run_n
            stats["step"] = f"grinding (remaining: {remaining})"
            print(f"\n{'='*40}\n  BATCH {run_n}  (remaining before: {remaining})\n{'='*40}")
            pause.wait()

            if stats["stop"]:
                print("Stop requested via overlay.")
                break

            # Decide up front whether this batch's bank visit needs to
            # withdraw the next one's bars, or whether a restock is coming
            # right after (which does its own withdraw at the end).
            need_restock = (remaining - config.GRIND_COUNT) < config.GRIND_COUNT

            if not run_sequence(withdraw_next=not need_restock):
                print("Sequence failed — stopping.")
                break

            remaining -= config.GRIND_COUNT

            if need_restock:
                stats["step"] = "restocking"
                print(f"\n{'='*40}\n  RESTOCK (qty {start_count})\n{'='*40}")
                if not restock_ge(start_count):
                    print("Restock failed — stopping.")
                    break
                remaining = start_count

            time.sleep(random.uniform(0.5, 1.2))

    except pause.ForceStop:
        print("Force stopped via overlay.")

    elapsed = time.time() - start_time
    h, rem = divmod(int(elapsed), 3600)
    m, s   = divmod(rem, 60)
    print(f"Session ended. Batches: {run_n} | Time: {h:02d}:{m:02d}:{s:02d}")
