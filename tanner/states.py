"""
Tanner control flow — states, transition table and per-session model.

Handlers live in tanner/run.py; this module stays free of screen/config
imports so it can be tested without a game or calibrated config.
Same-trigger transitions are evaluated in the order listed below.
"""
from transitions import Machine

MAX_CHARGES  = 6   # amulet of glory
CYCLE_START  = "walk_to_tanner"
FINAL_STATES = {"done", "stopped"}

STATES = ["start", "walk_to_tanner", "trade_ellis", "tanning", "walk_to_bank",
          "banking", "restock", "recover", "done", "stopped"]

_WALK_TRADE = ["walk_to_tanner", "trade_ellis", "walk_to_bank"]
_ACTIONS    = _WALK_TRADE + ["banking"]

TRANSITIONS = [
    {"trigger": "begin",   "source": "start",          "dest": "recover", "conditions": "start_from_ge"},
    {"trigger": "begin",   "source": "start",          "dest": "walk_to_tanner"},

    {"trigger": "ok",      "source": "walk_to_tanner", "dest": "trade_ellis"},
    {"trigger": "ok",      "source": "trade_ellis",    "dest": "tanning"},
    {"trigger": "ok",      "source": "tanning",        "dest": "walk_to_bank"},
    {"trigger": "ok",      "source": "walk_to_bank",   "dest": "banking"},
    {"trigger": "ok",      "source": "banking",        "dest": "walk_to_tanner", "after": "clear_skip_restock"},

    {"trigger": "restock", "source": "banking",        "dest": "restock",
     "conditions": ["restock_enabled", "has_charges"]},
    {"trigger": "restock", "source": "banking",        "dest": "stopped", "conditions": "restock_enabled",
     "after": "reason_no_charges_for_ge"},
    {"trigger": "restock", "source": "banking",        "dest": "done"},
    {"trigger": "ok",      "source": "restock",        "dest": "recover", "conditions": "has_charges",
     "after": "set_skip_restock"},
    {"trigger": "ok",      "source": "restock",        "dest": "stopped", "after": "reason_no_charges"},
    {"trigger": "fail",    "source": "restock",        "dest": "stopped", "after": "reason_restock_failed"},

    {"trigger": "fail",    "source": _WALK_TRADE,      "dest": "recover", "conditions": "has_charges"},
    {"trigger": "fail",    "source": "banking",        "dest": "recover", "conditions": "has_charges",
     "after": "set_skip_restock"},
    {"trigger": "fail",    "source": _ACTIONS,         "dest": "stopped", "after": "reason_no_charges"},
    {"trigger": "ok",      "source": "recover",        "dest": "walk_to_tanner"},
    {"trigger": "fail",    "source": "recover",        "dest": "stopped", "after": "reason_recover_failed"},

    {"trigger": "stop",    "source": CYCLE_START,      "dest": "stopped", "after": "reason_soft_stop"},
]


class TannerSession:
    def __init__(self, stats, restock_enabled, start_from_ge, charges):
        self.stats           = stats
        self.restock_enabled = restock_enabled
        self.start_from_ge   = start_from_ge
        self.charges         = charges
        self.skip_restock    = True   # first bank of a session skips the empty-slot check
        self.runs            = 0
        self.stop_reason     = None   # set when the session reaches done/stopped

    def has_charges(self):
        return self.charges > 0

    def on_enter_walk_to_tanner(self):
        self.runs += 1
        self.stats["run"] = self.runs

    def on_enter_recover(self):
        # Every glory teleport — failure recovery, post-GE return, Run-from-GE start.
        self.charges -= 1

    def set_skip_restock(self):
        # Only after a bank failure or GE restock (as the pre-state-machine loop did).
        self.skip_restock = True

    def clear_skip_restock(self):
        self.skip_restock = False

    def on_enter_restock(self):
        print("\n[RESTOCK] Bank slot 2 empty — heading to GE...")

    def on_enter_done(self):
        self.stop_reason = "out of hides, GE restock disabled"

    # Why the session stopped — attached to the transitions into `stopped`.
    def reason_no_charges_for_ge(self):
        self.stop_reason = "out of hides and no glory charges for the GE trip back"

    def reason_no_charges(self):
        self.stop_reason = "no glory charges left to recover"

    def reason_recover_failed(self):
        self.stop_reason = "recovery failed"

    def reason_restock_failed(self):
        self.stop_reason = "GE restock failed"

    def reason_soft_stop(self):
        self.stop_reason = "stopped via overlay"


def build_machine(stats, restock_enabled, start_from_ge, charges=MAX_CHARGES):
    """Build the session model and fire `begin` so the first real state's on_enter runs."""
    session = TannerSession(stats, restock_enabled, start_from_ge, charges)
    Machine(model=session, states=STATES, transitions=TRANSITIONS,
            initial="start", auto_transitions=False)
    session.trigger("begin")
    return session


def ok_or_fail(result):
    return "ok" if result else "fail"


def bank_event(result):
    """do_bank() returns True, False, or "restock"."""
    if result == "restock":
        return "restock"
    return ok_or_fail(result)
