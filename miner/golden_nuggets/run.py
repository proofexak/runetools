"""
Golden Nuggets session loop.
Control flow is the state machine in miner/golden_nuggets/states.py; this
module wires the real actions in as handlers.
"""
import time, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import lib.pause as pause
import lib.log as log
from lib.state_machine import run_machine
from lib.log import say
from miner.golden_nuggets.actions import (
    orient_south, orient_east, click_nearest_vein, wait_for_vein_depletion,
    count_filled_slots, deposit_to_hopper, process_full_sack,
    click_struts, wait_stopped,
)
from miner.golden_nuggets.states import (
    build_machine, mining_event, FINAL_STATES, CYCLE_START, DEPOSITS_PER_SACK,
)

os.makedirs(os.path.join(os.path.dirname(__file__), "log"), exist_ok=True)


def _elapsed(start):
    s = int(time.time() - start)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _handlers(session, stats, session_start):
    def seek_vein():
        before = count_filled_slots()
        if before >= 27:
            return "full"
        pos = click_nearest_vein()
        if pos is None:
            say("Retrying in 3s...")
            time.sleep(3)
            return "not_found"
        wait_stopped()
        session.vein_pos = pos
        session.vein_n += 1
        say(f"--- Vein #{session.vein_n}  (inv {before}/28, session {_elapsed(session_start)}) ---")
        return "ok"

    def mining():
        reason = wait_for_vein_depletion(session.vein_pos, stats)
        say(f"Vein #{session.vein_n} done  |  total {stats['run']}  reason={reason}")
        return mining_event(reason)

    def deposit():
        ok = deposit_to_hopper()
        if not ok:
            # A failed deposit usually means broken struts stopped the machine.
            say("Hopper full — fixing struts then retrying")
            orient_east()
            click_struts()
            ok = deposit_to_hopper()
        session.record_deposit(ok)   # only a successful (re)try counts toward the sack
        if not ok:
            if session.deposit_stuck():
                say(f"Hopper deposit failed {session.deposit_fails}x in a row — stopping")
            else:
                orient_south()
            return "fail"
        say(f"Hopper deposit #{session.hopper_deposits}/{DEPOSITS_PER_SACK}")
        orient_east()
        click_struts()
        if not session.sack_full():
            orient_south()
        return "ok"

    def process_sack():
        process_full_sack(stats)
        return "ok"

    return {"seek_vein": seek_vein, "mining": mining,
            "deposit": deposit, "process_sack": process_sack}


def run(stats):
    log.setup(os.path.join(os.path.dirname(__file__), "log", "golden_nuggets"))

    say("=== Golden Nuggets session starting — switch to OSRS (3s) ===")
    time.sleep(3)

    session_start = time.time()
    stats.update({"run": 0, "sack": 0, "step": "starting", "start": session_start, "stop": False})
    pause.reset()

    orient_south()
    say(f"Inventory at start: {count_filled_slots()}/28")

    session = build_machine(stats)
    try:
        final = run_machine(session, _handlers(session, stats, session_start),
                            stats, FINAL_STATES, CYCLE_START)
    except pause.ForceStop:
        say("Force stopped via overlay.")
        final = "stopped"
    last_step = stats["step"]
    stats["step"] = final

    say(f"Session ended ({final} after {last_step}). Veins: {session.vein_n} | "
         f"Ores: {stats['run']} | Time: {_elapsed(session_start)}")
