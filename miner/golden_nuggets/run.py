"""
Golden Nuggets session loop.
"""
import time, os, sys, random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import lib.pause as pause
import lib.log as log
from miner.golden_nuggets.miner import (
    orient_south, orient_east, click_nearest_vein, wait_for_vein_depletion,
    count_filled_slots, deposit_to_hopper, process_full_sack,
    check_and_fix_struts, wait_stopped, _log,
)

os.makedirs(os.path.join(os.path.dirname(__file__), "log"), exist_ok=True)


def _elapsed(start):
    s = int(time.time() - start)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def run(stats):
    log.setup(os.path.join(os.path.dirname(__file__), "log", "golden_nuggets"))

    _log("=== Golden Nuggets session starting — switch to OSRS (3s) ===")
    time.sleep(3)

    session_start = time.time()
    stats.update({"run": 0, "sack": 0, "step": "starting", "start": session_start, "stop": False})
    pause.reset()

    orient_south()
    starting_inv = count_filled_slots()
    _log(f"Inventory at start: {starting_inv}/28")
    vein_n = 0
    hopper_deposits = 0

    while not stats.get("stop"):
        pause.wait()
        stats["step"] = "seeking vein"

        before = count_filled_slots()
        if before >= 27:
            stats["step"] = "depositing"
            transferred = deposit_to_hopper()
            if not transferred:
                orient_south()
                continue
            hopper_deposits += 1
            stats["sack"] = hopper_deposits
            _log(f"Hopper deposit #{hopper_deposits}/4")

            orient_east()
            check_and_fix_struts()

            if hopper_deposits >= 4:
                stats["step"] = "processing sack"
                process_full_sack(stats)
                hopper_deposits = 0
                stats["sack"] = 0
            else:
                orient_south()
            continue

        pos = click_nearest_vein()
        if pos is None:
            _log("Retrying in 3s...")
            time.sleep(3)
            continue

        wait_stopped()

        vein_n += 1
        stats["step"] = "mining"
        _log(f"--- Vein #{vein_n}  (inv {before}/28, session {_elapsed(session_start)}) ---")

        reason = wait_for_vein_depletion(pos, stats)

        _log(f"Vein #{vein_n} done  |  total {stats['run']}  reason={reason}")
