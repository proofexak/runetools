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

_ACTIONS = ["walk_to_tanner", "trade_ellis", "walk_to_bank", "banking"]

TRANSITIONS = [
    {"trigger": "begin",   "source": "start",          "dest": "recover", "conditions": "start_from_ge"},
    {"trigger": "begin",   "source": "start",          "dest": "walk_to_tanner"},

    {"trigger": "ok",      "source": "walk_to_tanner", "dest": "trade_ellis"},
    {"trigger": "ok",      "source": "trade_ellis",    "dest": "tanning"},
    {"trigger": "ok",      "source": "tanning",        "dest": "walk_to_bank"},
    {"trigger": "ok",      "source": "walk_to_bank",   "dest": "banking"},
    {"trigger": "ok",      "source": "banking",        "dest": "walk_to_tanner", "after": "clear_skip_restock"},

    {"trigger": "restock", "source": "banking",        "dest": "restock", "conditions": "restock_enabled"},
    {"trigger": "restock", "source": "banking",        "dest": "done"},
    {"trigger": "ok",      "source": "restock",        "dest": "recover", "conditions": "has_charges"},
    {"trigger": "ok",      "source": "restock",        "dest": "stopped"},
    {"trigger": "fail",    "source": "restock",        "dest": "stopped"},

    {"trigger": "fail",    "source": _ACTIONS,         "dest": "recover", "conditions": "has_charges"},
    {"trigger": "fail",    "source": _ACTIONS,         "dest": "stopped"},
    {"trigger": "ok",      "source": "recover",        "dest": "walk_to_tanner"},
    {"trigger": "fail",    "source": "recover",        "dest": "stopped"},

    {"trigger": "stop",    "source": CYCLE_START,      "dest": "stopped"},
]


class TannerSession:
    def __init__(self, stats, restock_enabled, start_from_ge, charges):
        self.stats           = stats
        self.restock_enabled = restock_enabled
        self.start_from_ge   = start_from_ge
        self.charges         = charges
        self.skip_restock    = True   # first bank of a session skips the empty-slot check
        self.runs            = 0

    def has_charges(self):
        return self.charges > 0

    def on_enter_walk_to_tanner(self):
        self.runs += 1
        self.stats["run"] = self.runs

    def on_enter_recover(self):
        # Every glory teleport — failure recovery, post-GE return, Run-from-GE start.
        self.charges -= 1
        self.skip_restock = True

    def clear_skip_restock(self):
        self.skip_restock = False


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
