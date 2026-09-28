"""
Tanner bot session loop.
Called from root run.py after hide type is selected.
Control flow is the state machine in tanner/states.py; this module wires the
real actions in as handlers.
"""
import time, random, sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import lib.pause as pause
import lib.log as log
import tanner.config as config
from tanner.tanner import orient_west, walk_to_tanner, trade_ellis, walk_to_bank, do_bank, recover, _wait_stopped
from tanner.states import build_machine, ok_or_fail, bank_event, FINAL_STATES, CYCLE_START
from lib.state_machine import run_machine
from lib.ge import run_ge_flow

os.makedirs(os.path.join(os.path.dirname(__file__), "log"), exist_ok=True)


def _handlers(session):
    def tanning():
        _wait_stopped()
        return "ok"

    def banking():
        event = bank_event(do_bank(skip_restock_check=session.skip_restock))
        if event == "ok":
            time.sleep(random.uniform(0.5, 1.2))
        elif event == "restock":
            if session.restock_enabled:
                print("\n[RESTOCK] Bank slot 2 empty — heading to GE...")
            else:
                print("\n[DONE] Hides depleted and restock disabled — stopping.")
        return event

    def restock():
        # Return teleport goes through the recover state so it uses a glory charge.
        return ok_or_fail(run_ge_flow(config.HIDE_TYPE, on_complete=lambda: True))

    def recover_():
        print(f"\n[RECOVERY] Using charge ({session.charges} remaining after this)...")
        return ok_or_fail(recover())

    return {
        "walk_to_tanner": lambda: ok_or_fail(walk_to_tanner()),
        "trade_ellis":    lambda: ok_or_fail(trade_ellis()),
        "tanning":        tanning,
        "walk_to_bank":   lambda: ok_or_fail(walk_to_bank()),
        "banking":        banking,
        "restock":        restock,
        "recover":        recover_,
    }


def run(stats, start_from_ge=False):
    log.setup(os.path.join(os.path.dirname(__file__), "log", "tanner"))

    print(f"\nHide type: {config.HIDE_TYPE}")
    print("Starting in 3s — switch to OSRS. Press O to pause, P to force-stop.")
    time.sleep(3)

    stats.update({"run": 0, "step": "starting", "start": None, "stop": False})
    pause.reset()
    orient_west()

    start_time = time.time()
    stats["start"] = start_time
    session = build_machine(stats, config.RESTOCK_GE, start_from_ge)

    try:
        final = run_machine(session, _handlers(session), stats, FINAL_STATES, CYCLE_START)
    except pause.ForceStop:
        print("Force stopped via overlay.")
        final = "stopped"
    last_step = stats["step"]
    stats["step"] = final

    if final == "stopped" and session.charges <= 0:
        print("[RECOVERY] No charges remaining.")

    elapsed = time.time() - start_time
    h, rem = divmod(int(elapsed), 3600)
    m, s   = divmod(rem, 60)
    print(f"Session ended ({final} after {last_step}). Runs: {session.runs} | Time: {h:02d}:{m:02d}:{s:02d}")
