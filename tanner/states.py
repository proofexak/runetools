"""
Tanner control flow — states, transition table and per-session model.

Handlers live in tanner/run.py; this module stays free of screen/config
imports so it can be tested without a game or calibrated config.
Same-trigger transitions are evaluated in the order listed below.

The session starts where "Where are you?" says: GE → `ge_bank` (read the hide count
there: hides → glory to Al Kharid; the last 1 → restock right there), Al Kharid →
`walk_to_bank`. Every bank reads the hide count (`banking`, the bank inside `recover`,
`ge_bank`); the last 1 → `restock`. Only the bank right after a restock skips it.

A failed walk / trade / bank first goes to `look_around`: one look at the whole
screen for Ellis (blue) and the bank booth (purple), and the bot goes to
whichever it needs — Ellis while carrying hides, the booth while carrying
leather; the booth also works as a way back while carrying hides. Only when that
look finds nothing useful ("lost") does it spend a glory charge (`recover`).
One look per problem: it is allowed again after a tan or a recovery.
"""
from transitions import Machine

from lib.state_machine import ok_or_fail

MAX_CHARGES  = 6   # amulet of glory
CYCLE_START  = "walk_to_tanner"
FINAL_STATES = {"done", "stopped"}

STATES = ["start", "ge_bank", "walk_to_tanner", "trade_ellis", "tanning", "walk_to_bank",
          "banking", "restock", "look_around", "recover", "done", "stopped"]

_WALK_TRADE = ["walk_to_tanner", "trade_ellis", "walk_to_bank"]
_ACTIONS    = _WALK_TRADE + ["banking"]
# where the hide count is read: no count (the last 1, all-but-1 keeps it) → "restock"
_COUNTS     = ["banking", "recover", "ge_bank"]

# Config regions / points each state uses, drawn on its failure screenshot (lib/screenshots.py, PRO-91).
# "ge.X" / "energy.X" = lib/ge_config.py's / lib/energy_config.py's X.
STATE_MARKS = {
    "walk_to_tanner": ["TANNER_AREA", "CHARACTER", "INVENTORY_CHECK"],
    "trade_ellis":    ["ELLIS_REGION", "TANNING_CHECK"],
    "walk_to_bank":   ["BANK_REGION"],
    "banking":        ["BANK_REGION", "BANK_CHECK", "DEPOSIT_BTN", "HIDE_TAB", "BANK_SLOT_1", "HIDE_COUNT_REGION",
                       "energy.ENERGY_REGION", "energy.POTION_TAB", "energy.STAMINA_POTION_SLOT"],   # stamina top-up
    "look_around":    ["CHARACTER"],
    "recover":        ["AMULET_SLOT", "DOUBLE_DOORS_REGION", "TP_BANK_REGION", "TP_BOOTH_REGION", "BANK_CHECK"],
    "ge_bank":        ["ge.GE_REGION", "ge.BANK_CHECK", "HIDE_TAB", "HIDE_COUNT_REGION"],
    "restock":        ["ge.GE_APPROACH_REGION", "ge.GE_REGION", "ge.BANK_CHECK", "ge.GE_CHECK",
                       "HIDE_TAB", "BANK_SLOT_2", "SELL_INV_SLOT"],
}

TRANSITIONS = [
    # "Where are you?" — GE: read the hide count at the GE bank; Al Kharid: click the booth first
    {"trigger": "begin",   "source": "start",          "dest": "ge_bank", "conditions": "at_ge"},
    {"trigger": "begin",   "source": "start",          "dest": "walk_to_bank"},
    {"trigger": "ok",      "source": "ge_bank",        "dest": "recover", "conditions": "has_charges",
     "after": "set_skip_restock"},                                             # glory to Al Kharid
    {"trigger": "ok",      "source": "ge_bank",        "dest": "stopped", "after": "reason_no_charges"},
    {"trigger": "fail",    "source": "ge_bank",        "dest": "stopped", "after": "reason_ge_bank_failed"},

    {"trigger": "ok",      "source": "walk_to_tanner", "dest": "trade_ellis"},
    {"trigger": "ok",      "source": "trade_ellis",    "dest": "tanning"},
    {"trigger": "ok",      "source": "tanning",        "dest": "walk_to_bank"},
    {"trigger": "ok",      "source": "walk_to_bank",   "dest": "banking"},
    {"trigger": "ok",      "source": "banking",        "dest": "walk_to_tanner", "after": "clear_skip_restock"},

    {"trigger": "restock", "source": _COUNTS,          "dest": "restock",
     "conditions": ["restock_enabled", "has_charges"]},
    {"trigger": "restock", "source": _COUNTS,          "dest": "stopped", "conditions": "restock_enabled",
     "after": "reason_no_charges_for_ge"},
    {"trigger": "restock", "source": _COUNTS,          "dest": "done"},
    {"trigger": "ok",      "source": "restock",        "dest": "recover", "conditions": "has_charges",
     "after": "set_skip_restock"},
    {"trigger": "ok",      "source": "restock",        "dest": "stopped", "after": "reason_no_charges"},
    {"trigger": "fail",    "source": "restock",        "dest": "stopped", "after": "reason_restock_failed"},

    # a failure: look around first (once per problem), the glory teleport only if that finds nothing
    {"trigger": "fail",    "source": ["walk_to_tanner", "trade_ellis"], "dest": "look_around",
     "conditions": "can_look", "after": "need_ellis"},
    {"trigger": "fail",    "source": ["walk_to_bank", "banking"], "dest": "look_around",
     "conditions": "can_look", "after": "need_bank"},
    {"trigger": "tanned",  "source": "look_around",    "dest": "tanning"},     # found Ellis and traded
    {"trigger": "bank",    "source": "look_around",    "dest": "banking"},     # clicked the booth
    {"trigger": "lost",    "source": "look_around",    "dest": "recover", "conditions": "has_charges"},
    {"trigger": "lost",    "source": "look_around",    "dest": "stopped", "after": "reason_no_charges"},

    {"trigger": "fail",    "source": _ACTIONS,         "dest": "recover", "conditions": "has_charges"},
    {"trigger": "fail",    "source": _ACTIONS,         "dest": "stopped", "after": "reason_no_charges"},
    {"trigger": "ok",      "source": "recover",        "dest": "walk_to_tanner", "after": "clear_skip_restock"},
    {"trigger": "fail",    "source": "recover",        "dest": "stopped", "after": "reason_recover_failed"},

    {"trigger": "stop",    "source": CYCLE_START,      "dest": "stopped", "after": "reason_soft_stop"},
]


class TannerSession:
    def __init__(self, stats, restock_enabled, at_ge, charges):
        self.stats           = stats
        self.restock_enabled = restock_enabled
        self.at_ge           = at_ge  # "Where are you?" → GE: no ring teleport for a restock from there
        self.charges         = charges
        self.skip_restock    = False  # every bank reads the hide count, except right after a restock
        self.runs            = 0
        self.stop_reason     = None   # set when the session reaches done/stopped
        self.looked          = False  # looked around since the last tan / recovery
        self.need            = None   # what look_around goes for: "ellis" or "bank"
        self.restock_error   = None   # why the last GE restock failed (lib.ge.run_ge_flow)

    def has_charges(self):
        return self.charges > 0

    def can_look(self):
        return not self.looked

    def need_ellis(self):
        self.need = "ellis"    # failed on the way to / at Ellis: carrying hides

    def need_bank(self):
        self.need = "bank"     # failed on the way to / at the bank: carrying leather

    def on_enter_look_around(self):
        self.looked = True

    def on_enter_tanning(self):
        self.looked = False    # a trip worked: a later problem gets its own look

    def on_enter_walk_to_tanner(self):
        self.runs += 1
        self.stats["run"] = self.runs

    def on_enter_recover(self):
        # Every glory teleport — failure recovery, the way back after a restock, a start at the GE.
        self.charges -= 1
        self.looked = False    # a fresh start at the bank: a later problem gets its own look
        self.at_ge = False     # it lands in Al Kharid: a later restock rings to the GE again

    def set_skip_restock(self):
        # The hide count was just read (GE bank) or just topped up (a restock): the next bank —
        # the one inside the recovery — doesn't read it again.
        self.skip_restock = True

    def clear_skip_restock(self):
        self.skip_restock = False

    def on_enter_restock(self):
        if self.at_ge:
            print("\n[RESTOCK] Out of hides — restocking here at the GE...")
        else:
            print("\n[RESTOCK] Out of hides — heading to GE...")

    def on_enter_done(self):
        self.stop_reason = "out of hides, GE restock disabled"

    # Why the session stopped — attached to the transitions into `stopped`.
    def reason_no_charges_for_ge(self):
        self.stop_reason = "out of hides and no glory charges for the GE trip back"

    def reason_no_charges(self):
        self.stop_reason = "no glory charges left to recover"

    def reason_recover_failed(self):
        self.stop_reason = "recovery failed"

    def reason_ge_bank_failed(self):
        self.stop_reason = "GE bank not found"

    def reason_restock_failed(self):
        self.stop_reason = f"GE restock failed: {self.restock_error}" if self.restock_error \
            else "GE restock failed"

    def reason_soft_stop(self):
        self.stop_reason = "stopped via overlay"


def build_machine(stats, restock_enabled, at_ge=False, charges=MAX_CHARGES):
    """Build the session model and fire `begin` so the first real state's on_enter runs.
    at_ge: the answer to "Where are you?" was GE."""
    session = TannerSession(stats, restock_enabled, at_ge, charges)
    Machine(model=session, states=STATES, transitions=TRANSITIONS,
            initial="start", auto_transitions=False)
    session.trigger("begin")
    return session


def bank_event(result):
    """do_bank() returns True, False, or "restock"."""
    if result == "restock":
        return "restock"
    return ok_or_fail(result)


def recovery_drill(handlers, stats):
    """Wrap a session's handlers for a test run of the glory recovery: the opening
    bank and one full trip run as normal, then the trip's (real) bank reports
    "fail" and the look-around reports "lost" (without looking) so the table goes
    to recover, and after recovery the session stops at walk_to_tanner. Spends one
    charge. Used by tanner/checks/recovery_drill.py."""
    banks = [0]
    bank, recover = handlers["banking"], handlers["recover"]

    def banking():
        banks[0] += 1
        event = bank()
        return "fail" if banks[0] == 2 and event == "ok" else event

    def recover_():
        event = recover()
        stats["stop"] = True
        return event

    return {**handlers, "banking": banking, "look_around": lambda: "lost", "recover": recover_}
