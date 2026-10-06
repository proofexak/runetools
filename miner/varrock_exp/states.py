"""
Varrock Exp control flow — two-rock mine-and-drop cycle.

Handlers live in miner/varrock_exp/run.py; this module stays free of
screen/config imports so it can be tested without a game or calibrated config.
"""
from transitions import Machine

CYCLE_START  = {"mine_first", "mine_second"}   # overlay Stop is honoured before either rock
FINAL_STATES = {"stopped"}

STATES = ["mine_first", "drop_first", "mine_second", "drop_second", "stopped"]

TRANSITIONS = [
    {"trigger": "ok",        "source": "mine_first",  "dest": "drop_first"},
    {"trigger": "not_found", "source": "mine_first",  "dest": "mine_first"},
    {"trigger": "ok",        "source": "drop_first",  "dest": "mine_second"},
    {"trigger": "ok",        "source": "mine_second", "dest": "drop_second"},
    {"trigger": "not_found", "source": "mine_second", "dest": "mine_first"},
    {"trigger": "ok",        "source": "drop_second", "dest": "mine_first"},
    {"trigger": "stop",      "source": list(CYCLE_START), "dest": "stopped"},
]


class VarrockSession:
    def __init__(self, stats):
        self.stats = stats
        self.ores  = 0

    def count_drop(self, found):
        """One ore per drop, from either rock (the old loop only counted the second
        rock's, so it reported about half the ore mined)."""
        if found:
            self.ores += 1
            self.stats["run"] = self.ores


def build_machine(stats):
    session = VarrockSession(stats)
    Machine(model=session, states=STATES, transitions=TRANSITIONS,
            initial="mine_first", auto_transitions=False)
    return session
