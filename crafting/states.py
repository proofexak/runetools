"""
Crafting (Path of Exile) control flow — grab currency once, then one item per
pass through `craft` until the list is done.

Handlers live in crafting/run.py; this module stays free of screen/config
imports so it can be tested without a game or calibrated config.
"""
from transitions import Machine

CYCLE_START  = "craft"            # overlay Stop is honoured before each item
FINAL_STATES = {"done", "stopped"}

STATES = ["grab_currency", "craft", "done", "stopped"]

TRANSITIONS = [
    {"trigger": "ok",   "source": "grab_currency", "dest": "craft", "conditions": "has_more"},
    {"trigger": "ok",   "source": "grab_currency", "dest": "done"},
    {"trigger": "ok",   "source": "craft",         "dest": "craft", "conditions": "has_more"},
    {"trigger": "ok",   "source": "craft",         "dest": "done"},
    {"trigger": "stop", "source": CYCLE_START,     "dest": "stopped"},
]


class CraftingSession:
    def __init__(self, stats, items):
        self.stats = stats
        self.items = [item for item in items if not item.get("skip")]
        self.total = len(self.items)
        self.index = 0            # items finished

    def has_more(self):
        return self.index < self.total

    def next_item(self):
        n = self.index + 1
        self.stats["run"] = n
        self.stats["step"] = f"item {n}/{self.total}"
        return self.items[self.index]

    def item_done(self):
        self.index += 1

    def on_enter_done(self):
        print("\nAll items done.")


def build_machine(stats, items):
    session = CraftingSession(stats, items)
    Machine(model=session, states=STATES, transitions=TRANSITIONS,
            initial="grab_currency", auto_transitions=False)
    return session
