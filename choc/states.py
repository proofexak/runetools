"""
Choco Grind control flow — states, transition table and per-session model.

Handlers live in choc/run.py; this module stays free of screen/config imports so it
can be tested without a game or calibrated config. Same-trigger transitions are
evaluated in the order listed below.

    start → withdraw ─ok→ grind ─ok→ grind                    (next batch)
                                 └ok, restock due→ restock ─ok→ grind
    withdraw / grind / restock ─fail→ stopped                 (with the reason)
    grind ─stop→ stopped                                      (overlay Stop, before a batch)

The bar count works as the old loop did: `remaining` starts at the count entered at
launch, every ground batch takes GRIND_COUNT off it, and when fewer than a batch would
be left after the next one, that batch's bank visit skips withdrawing (the GE restock
right after buys `start_count` bars and withdraws them) and `remaining` resets.
"""
from transitions import Machine

from choc.logic import restock_due

CYCLE_START  = "grind"
FINAL_STATES = {"stopped"}

STATES = ["start", "withdraw", "grind", "restock", "stopped"]

TRANSITIONS = [
    {"trigger": "begin", "source": "start",    "dest": "withdraw"},

    {"trigger": "ok",    "source": "withdraw", "dest": "grind"},
    {"trigger": "fail",  "source": "withdraw", "dest": "stopped", "after": "reason_withdraw_failed"},

    {"trigger": "ok",    "source": "grind",    "dest": "restock", "conditions": "restock_after",
     "before": "ground_batch"},
    {"trigger": "ok",    "source": "grind",    "dest": "grind",   "before": "ground_batch"},
    {"trigger": "fail",  "source": "grind",    "dest": "stopped", "after": "reason_sequence_failed"},

    {"trigger": "ok",    "source": "restock",  "dest": "grind",   "before": "restocked"},
    {"trigger": "fail",  "source": "restock",  "dest": "stopped", "after": "reason_restock_failed"},

    {"trigger": "stop",  "source": CYCLE_START, "dest": "stopped", "after": "reason_soft_stop"},
]


class ChocSession:
    def __init__(self, stats, start_count, grind_count):
        self.stats         = stats
        self.start_count   = start_count
        self.grind_count   = grind_count
        self.remaining     = start_count   # bars left before the next GE restock
        self.batches       = 0             # batches ground (stats["run"])
        self.restock_after = False         # this batch's bank visit is followed by a restock
        self.stop_reason   = None
        self.restock_error = None          # why the last GE restock failed

    def on_enter_grind(self):
        # decided up front: if a restock follows, this batch's bank visit doesn't withdraw
        self.restock_after = restock_due(self.remaining, self.grind_count)

    def ground_batch(self):
        self.batches += 1
        self.stats["run"] = self.batches
        self.remaining -= self.grind_count

    def restocked(self):
        self.remaining = self.start_count

    def reason_withdraw_failed(self):
        self.stop_reason = "could not withdraw the starting chocolate"

    def reason_sequence_failed(self):
        self.stop_reason = "grind / bank sequence failed"

    def reason_restock_failed(self):
        self.stop_reason = f"GE restock failed: {self.restock_error}" if self.restock_error             else "GE restock failed"

    def reason_soft_stop(self):
        self.stop_reason = "stopped via overlay"


def build_machine(stats, start_count, grind_count):
    """Build the session model and fire `begin` so the first real state's on_enter runs."""
    session = ChocSession(stats, start_count, grind_count)
    Machine(model=session, states=STATES, transitions=TRANSITIONS,
            initial="start", auto_transitions=False)
    session.trigger("begin")
    return session
