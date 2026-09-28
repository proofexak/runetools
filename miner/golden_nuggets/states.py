"""
Golden Nuggets control flow — states, transition table and per-session model.

Handlers live in miner/golden_nuggets/run.py; this module stays free of
screen/config imports so it can be tested without a game or calibrated config.
Same-trigger transitions are evaluated in the order listed below.
"""
from transitions import Machine

DEPOSITS_PER_SACK = 4
MAX_DEPOSIT_FAILS = 3   # consecutive — hopper highlight off or HOPPER_REGION miscalibrated
CYCLE_START       = "seek_vein"
FINAL_STATES      = {"stopped"}

STATES = ["seek_vein", "mining", "deposit", "process_sack", "stopped"]

TRANSITIONS = [
    {"trigger": "full",      "source": "seek_vein",    "dest": "deposit"},
    {"trigger": "ok",        "source": "seek_vein",    "dest": "mining"},
    {"trigger": "not_found", "source": "seek_vein",    "dest": "seek_vein"},
    {"trigger": "full",      "source": "mining",       "dest": "deposit"},
    {"trigger": "ok",        "source": "mining",       "dest": "seek_vein"},
    {"trigger": "ok",        "source": "deposit",      "dest": "process_sack", "conditions": "sack_full"},
    {"trigger": "ok",        "source": "deposit",      "dest": "seek_vein"},
    {"trigger": "fail",      "source": "deposit",      "dest": "stopped",   "conditions": "deposit_stuck"},
    {"trigger": "fail",      "source": "deposit",      "dest": "seek_vein"},
    {"trigger": "ok",        "source": "process_sack", "dest": "seek_vein"},
    {"trigger": "stop",      "source": CYCLE_START,    "dest": "stopped"},
]


class NuggetsSession:
    def __init__(self, stats):
        self.stats           = stats
        self.vein_pos        = None
        self.vein_n          = 0
        self.hopper_deposits = 0
        self.deposit_fails   = 0   # consecutive failed hopper deposits

    def sack_full(self):
        return self.hopper_deposits >= DEPOSITS_PER_SACK

    def deposit_stuck(self):
        return self.deposit_fails >= MAX_DEPOSIT_FAILS


def build_machine(stats):
    session = NuggetsSession(stats)
    Machine(model=session, states=STATES, transitions=TRANSITIONS,
            initial="seek_vein", auto_transitions=False)
    return session


def mining_event(reason):
    """wait_for_vein_depletion() reason -> event."""
    return "full" if reason == "full" else "ok"
