"""
Chocolate dust bot session loop.
Called from root run.py after the per-restock bar count is entered.
Control flow is the state machine in choc/states.py; this module wires the real
actions in as handlers.
"""
import time, random, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import choc.config as config
from choc.choc import run_sequence, bootstrap_withdraw, restock_ge, bar_count_calibrated, bar_slot_calibrated
from choc.states import build_machine, bank_event, FINAL_STATES, CYCLE_START
from lib.session import run_session
import lib.human as human

os.makedirs(os.path.join(os.path.dirname(__file__), "log"), exist_ok=True)


def _handlers(session):
    def withdraw():
        return bank_event(bootstrap_withdraw())

    def grind():
        print(f"\n{'='*40}\n  BATCH {session.batches + 1}\n{'='*40}")
        event = bank_event(run_sequence())
        if event == "fail":
            print("Sequence failed — stopping.")
        else:
            human.sleep(0.5, 1.2)
        return event

    def restock():
        print(f"\n{'='*40}\n  RESTOCK (qty {session.restock_count})\n{'='*40}")
        ok, session.restock_error = restock_ge(session.restock_count)
        if not ok:
            print(f"Restock failed ({session.restock_error}) — stopping.")
            return "fail"
        human.sleep(0.5, 1.2)
        return "ok"

    return {"withdraw": withdraw, "grind": grind, "restock": restock}


def _summary(session, final, last_step):
    if final == "stopped" and session.stop_reason is None:
        session.stop_reason = "force-stopped (P)"
    print(f"\n[{final.upper()}] {session.stop_reason}")
    return f"Batches: {session.batches} ({session.batches * session.grind_count} bars ground)"


def run(stats, restock_count):
    # Runs indefinitely — when a bank visit sees no count on the chocolate bars, a GE restock
    # buys `restock_count` more. Ends on the overlay's Stop (before the next batch), P, a failed
    # bank / GE step, or out of bars with RESTOCK_GE off.
    if not bar_count_calibrated():
        # without it the bot can't see it's out of bars
        print("\n[CHOC] Calibrate the Chocolate Count Region first (Choco Grind ⚙ → Bank → Chocolate Count"
              " Region):\n  a box over the count on the chocolate bar stack — that's how the bot sees it's"
              " out of bars.")
        return
    if not bar_slot_calibrated():
        # without it a batch under 27 bars leaves slot 27 empty and the bot loops forever
        print("\n[CHOC] Calibrate the Empty Slot Color first (Choco Grind ⚙ → Inventory → Empty Slot Color):\n"
              "  click an empty inventory slot — that's how the bot sees a batch is short of 27 bars.")
        return
    restock_enabled = getattr(config, "RESTOCK_GE", True)
    run_session(
        stats,
        bot          = "choc",
        params       = {"restock_count": restock_count, "grind_count": config.GRIND_COUNT,
                        "restock_ge": restock_enabled},
        log_prefix   = os.path.join(os.path.dirname(__file__), "log", "choc"),
        intro        = [f"\nChocolate bars per restock: {restock_count}"],
        setup        = lambda: None,
        session      = lambda: build_machine(stats, restock_count, config.GRIND_COUNT, restock_enabled),
        handlers     = _handlers,
        final_states = FINAL_STATES,
        cycle_start  = CYCLE_START,
        summary      = _summary,
    )
