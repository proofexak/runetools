"""
Tanner control flow — states, transition table and per-session model.

Handlers live in tanner/run.py; this module stays free of screen/config
imports so it can be tested without a game or calibrated config.
Same-trigger transitions are evaluated in the order listed below.

A failed walk / trade / bank first goes to `look_around`: one look at the whole
screen for Ellis (blue) and the bank booth (purple), and the bot goes to
whichever it needs — Ellis while carrying hides, the booth while carrying
leather; the booth also works as a way back while carrying hides. Only when that
look finds nothing useful ("lost") does it spend a glory charge (`recover`).
One look per problem: it is allowed again after a tan or a recovery.
"""
import math

from transitions import Machine

from lib.state_machine import ok_or_fail

MAX_CHARGES  = 6   # amulet of glory
HIDES_PER_TRIP = 27   # an inventory: 28 slots, one holds the coins
CYCLE_START  = "walk_to_tanner"
FINAL_STATES = {"done", "stopped"}

STATES = ["start", "walk_to_tanner", "trade_ellis", "tanning", "walk_to_bank",
          "banking", "restock", "look_around", "recover", "done", "stopped"]

_WALK_TRADE = ["walk_to_tanner", "trade_ellis", "walk_to_bank"]
_ACTIONS    = _WALK_TRADE + ["banking"]

TRANSITIONS = [
    # GE mode: a buy-only restock first (ring to the GE, buy hides with the coins carried), then glory back
    {"trigger": "begin",   "source": "start",          "dest": "restock", "conditions": "start_from_ge"},
    {"trigger": "begin",   "source": "start",          "dest": "walk_to_bank"},   # open the bank, deposit + withdraw first

    {"trigger": "ok",      "source": "walk_to_tanner", "dest": "trade_ellis"},
    {"trigger": "ok",      "source": "trade_ellis",    "dest": "tanning"},
    {"trigger": "ok",      "source": "tanning",        "dest": "walk_to_bank"},
    {"trigger": "ok",      "source": "walk_to_bank",   "dest": "banking"},
    # GE mode: once the hides it bought are tanned, the bank visit only deposits and the session ends
    {"trigger": "ok",      "source": "banking",        "dest": "done", "conditions": "tanned_enough",
     "after": "reason_tanned_bought"},
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

    # a failure: look around first (once per problem), the glory teleport only if that finds nothing
    {"trigger": "fail",    "source": ["walk_to_tanner", "trade_ellis"], "dest": "look_around",
     "conditions": "can_look", "after": "need_ellis"},
    {"trigger": "fail",    "source": "walk_to_bank",   "dest": "look_around", "conditions": "can_look",
     "after": "need_bank"},
    {"trigger": "fail",    "source": "banking",        "dest": "look_around", "conditions": "can_look",
     "after": ["set_skip_restock", "need_bank"]},
    {"trigger": "tanned",  "source": "look_around",    "dest": "tanning"},     # found Ellis and traded
    {"trigger": "bank",    "source": "look_around",    "dest": "banking"},     # clicked the booth
    {"trigger": "lost",    "source": "look_around",    "dest": "recover", "conditions": "has_charges"},
    {"trigger": "lost",    "source": "look_around",    "dest": "stopped", "after": "reason_no_charges"},

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
        self.looked          = False  # looked around since the last tan / recovery
        self.need            = None   # what look_around goes for: "ellis" or "bank"
        self.restock_error   = None   # why the last GE restock failed (lib.ge.run_ge_flow)
        self.buy_only        = start_from_ge   # GE mode: the first restock only buys
        self.tans            = 0      # inventories tanned this session
        self.tan_target      = None   # GE mode: stop once `tans` reaches this (set by bought())
        self.bought_qty      = None

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
        self.tans += 1

    def bought(self, quantity):
        """GE mode's buy went through: tan exactly the inventories those hides make."""
        self.bought_qty = quantity
        self.tan_target = self.tans + math.ceil(quantity / HIDES_PER_TRIP)

    def tanned_enough(self):
        return self.tan_target is not None and self.tans >= self.tan_target

    def on_enter_walk_to_tanner(self):
        self.runs += 1
        self.stats["run"] = self.runs

    def on_enter_recover(self):
        # Every glory teleport — failure recovery, post-GE return, Run-from-GE start.
        self.charges -= 1
        self.looked = False    # a fresh start at the bank: a later problem gets its own look

    def set_skip_restock(self):
        # Only after a bank failure or GE restock (as the pre-state-machine loop did).
        self.skip_restock = True

    def clear_skip_restock(self):
        self.skip_restock = False

    def on_enter_restock(self):
        if self.buy_only:
            print("\n[RESTOCK] GE mode — to the GE to buy hides first...")
        else:
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
        self.stop_reason = f"GE restock failed: {self.restock_error}" if self.restock_error \
            else "GE restock failed"

    def reason_tanned_bought(self):
        self.stop_reason = f"tanned the {self.bought_qty} hides bought ({self.tan_target} trips)"

    def reason_soft_stop(self):
        self.stop_reason = "stopped via overlay"


def build_machine(stats, restock_enabled, start_from_ge, charges=MAX_CHARGES):
    """Build the session model and fire `begin` so the first real state's on_enter runs."""
    session = TannerSession(stats, restock_enabled, start_from_ge, charges)
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
