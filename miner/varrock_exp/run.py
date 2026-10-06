"""
Varrock Exp session loop.
Control flow is the state machine in miner/varrock_exp/states.py; this module
wires the real actions in as handlers.
"""
import time, sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib.session import run_session
from lib.mouse import release_key
from miner.varrock_exp.actions import orient_south, click_magenta_rock, click_blue_rock, wait_and_drop
from miner.varrock_exp.states import build_machine, FINAL_STATES, CYCLE_START

os.makedirs(os.path.join(os.path.dirname(__file__), "log"), exist_ok=True)


def _mine(stats, first, second, first_label, second_label):
    """Click the preferred rock, falling back to the other colour."""
    stats["step"] = f"{first_label} rock"
    if first():
        return "ok"
    print(f"  {first_label.title()} not found — trying {second_label}")
    stats["step"] = f"{second_label} rock (fallback)"
    if second():
        return "ok"
    print("  No rocks found — waiting 10s")
    time.sleep(10)
    return "not_found"


def _handlers(session):
    stats = session.stats

    def drop():
        session.count_drop(found=wait_and_drop())
        return "ok"

    return {
        "mine_first":  lambda: _mine(stats, click_magenta_rock, click_blue_rock, "magenta", "blue"),
        "drop_first":  drop,
        "mine_second": lambda: _mine(stats, click_blue_rock, click_magenta_rock, "blue", "magenta"),
        "drop_second": drop,
    }


def run(stats):
    run_session(
        stats,
        bot          = "varrock_exp",
        log_prefix   = os.path.join(os.path.dirname(__file__), "log", "varrock_exp"),
        intro        = ["=== Varrock Exp session ==="],
        setup        = orient_south,
        session      = lambda: build_machine(stats),
        handlers     = _handlers,
        final_states = FINAL_STATES,
        cycle_start  = CYCLE_START,
        summary      = lambda session, final, last: f"Ores dropped: {session.ores}",
        teardown     = lambda: release_key("shift"),   # never leave a shift-drop held
    )
