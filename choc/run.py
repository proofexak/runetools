"""
Chocolate dust bot session loop.
Called from root run.py after the starting chocolate count is entered.
Control flow is the state machine in choc/states.py; this module wires the real
actions in as handlers.
"""
import time, random, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import choc.config as config
from choc.choc import run_sequence, bootstrap_withdraw, restock_ge
from choc.states import build_machine, FINAL_STATES, CYCLE_START
from lib.session import run_session
from lib.state_machine import ok_or_fail

os.makedirs(os.path.join(os.path.dirname(__file__), "log"), exist_ok=True)


def _handlers(session):
    def withdraw():
        return ok_or_fail(bootstrap_withdraw())

    def grind():
        print(f"\n{'='*40}\n  BATCH {session.batches + 1}  (remaining before: {session.remaining})\n{'='*40}")
        if not run_sequence(withdraw_next=not session.restock_after):
            print("Sequence failed — stopping.")
            return "fail"
        time.sleep(random.uniform(0.5, 1.2))
        return "ok"

    def restock():
        print(f"\n{'='*40}\n  RESTOCK (qty {session.start_count})\n{'='*40}")
        ok, session.restock_error = restock_ge(session.start_count)
        if not ok:
            print(f"Restock failed ({session.restock_error}) — stopping.")
            return "fail"
        time.sleep(random.uniform(0.5, 1.2))
        return "ok"

    return {"withdraw": withdraw, "grind": grind, "restock": restock}


def _summary(session, final, last_step):
    if final == "stopped" and session.stop_reason is None:
        session.stop_reason = "force-stopped (P)"
    print(f"\n[{final.upper()}] {session.stop_reason}")
    return f"Batches: {session.batches} ({session.batches * session.grind_count} bars ground)"


def run(stats, start_count):
    # Runs indefinitely — once the starting bars are ground through, a GE restock buys
    # `start_count` more and the count resets. Ends on the overlay's Stop (before the
    # next batch), P, or a failed bank / GE step.
    run_session(
        stats,
        bot          = "choc",
        params       = {"start_count": start_count, "grind_count": config.GRIND_COUNT},
        log_prefix   = os.path.join(os.path.dirname(__file__), "log", "choc"),
        intro        = [f"\nStarting chocolate: {start_count}"],
        setup        = lambda: None,
        session      = lambda: build_machine(stats, start_count, config.GRIND_COUNT),
        handlers     = _handlers,
        final_states = FINAL_STATES,
        cycle_start  = CYCLE_START,
        summary      = _summary,
    )
