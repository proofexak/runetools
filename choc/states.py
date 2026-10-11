"""
Choco Grind control flow — states, transition table and per-session model.
Handlers live in choc/run.py; this module stays free of screen/config imports so it
can be tested without a game or calibrated config. Same-trigger transitions are
evaluated in the order listed below.

    start → withdraw ─ok→ grind ─ok→ grind                    (next batch)
                    └restock→ restock ─ok→ grind
                               grind ─restock→ restock
    withdraw / grind ─restock, RESTOCK_GE off→ stopped        (out of chocolate bars)
    withdraw / grind / restock ─fail→ stopped                 (with the reason)
    grind ─stop→ stopped                                      (overlay Stop, before a batch)

When to restock is read off the bank, like tanner: every bank visit (the first one, and the
one after each batch) looks at the chocolate bar stack's count before withdrawing. A count →
withdraw the next batch ("ok"); none (1 or 0 left — OSRS draws no number on a 1) →
"restock", with the bank left open for the GE trip. The restock buys `restock_count` bars
(asked at launch) and its own bank visit withdraws the next batch, so it leads to grind.
"""
from transitions import Machine

CYCLE_START  = "grind"
FINAL_STATES = {"stopped"}

STATES = ["start", "withdraw", "grind", "restock", "stopped"]

TRANSITIONS = [
    {"trigger": "begin",   "source": "start",    "dest": "withdraw"},

    {"trigger": "ok",      "source": "withdraw", "dest": "grind"},
    {"trigger": "restock", "source": "withdraw", "dest": "restock", "conditions": "restock_enabled"},
    {"trigger": "restock", "source": "withdraw", "dest": "stopped", "after": "reason_out_of_bars"},
    {"trigger": "fail",    "source": "withdraw", "dest": "stopped", "after": "reason_withdraw_failed"},

    # a grind is a batch plus the bank visit after it: "restock" still ground its batch
    {"trigger": "ok",      "source": "grind",    "dest": "grind",   "before": "ground_batch"},
    {"trigger": "restock", "source": "grind",    "dest": "restock", "conditions": "restock_enabled",
     "before": "ground_batch"},
    {"trigger": "restock", "source": "grind",    "dest": "stopped", "before": "ground_batch",
     "after": "reason_out_of_bars"},
    {"trigger": "fail",    "source": "grind",    "dest": "stopped", "after": "reason_sequence_failed"},

    {"trigger": "ok",      "source": "restock",  "dest": "grind"},
    {"trigger": "fail",    "source": "restock",  "dest": "stopped", "after": "reason_restock_failed"},

    {"trigger": "stop",    "source": CYCLE_START, "dest": "stopped", "after": "reason_soft_stop"},
]


class ChocSession:
    def __init__(self, stats, restock_count, grind_count, restock_enabled):
        self.stats           = stats
        self.restock_count   = restock_count    # bars bought per GE restock (asked at launch)
        self.grind_count     = grind_count
        self.restock_enabled = restock_enabled  # False: out of bars stops instead (RESTOCK_GE)
        self.batches         = 0                # batches ground (stats["run"])
        self.stop_reason     = None
        self.restock_error   = None             # why the last GE restock failed

    def ground_batch(self):
        self.batches += 1
        self.stats["run"] = self.batches

    def reason_out_of_bars(self):
        self.stop_reason = "out of chocolate bars (RESTOCK_GE is off)"

    def reason_withdraw_failed(self):
        self.stop_reason = "could not withdraw the starting chocolate"

    def reason_sequence_failed(self):
        self.stop_reason = "grind / bank sequence failed"

    def reason_restock_failed(self):
        self.stop_reason = f"GE restock failed: {self.restock_error}" if self.restock_error \
            else "GE restock failed"

    def reason_soft_stop(self):
        self.stop_reason = "stopped via overlay"


def build_machine(stats, restock_count, grind_count, restock_enabled=True):
    """Build the session model and fire `begin` so the first real state's on_enter runs."""
    session = ChocSession(stats, restock_count, grind_count, restock_enabled)
    Machine(model=session, states=STATES, transitions=TRANSITIONS,
            initial="start", auto_transitions=False)
    session.trigger("begin")
    return session


def bank_event(result):
    """A bank visit returns True, False, or "restock" (like tanner's do_bank)."""
    if result == "restock":
        return "restock"
    return "ok" if result else "fail"
