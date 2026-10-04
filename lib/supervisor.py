"""
Restart policy for unattended runs (lib/headless.py) — pure: no screen, no
sleeping, no processes. Clocks are passed in so tests control time.
"""
from collections import deque
from typing import NamedTuple, Optional

BACKOFF_START       = 30     # s before the first automatic restart / login retry
BACKOFF_MAX         = 600    # backoff cap
LONG_SESSION        = 600    # a session this long resets the backoff
BUDGET              = 5      # automatic restarts allowed ...
BUDGET_WINDOW       = 3600   # ... per rolling hour
MAX_LOGIN_FAILURES  = 3      # consecutive failed logins before going idle
CREDENTIALS_RECHECK = 60     # s between checks for RuneLite's saved credentials


class Outcome(NamedTuple):
    final: str               # session's final state ("crashed" if it raised)
    reason: Optional[str]    # the bot's stop_reason, if any
    crashed: bool            # ended with an unexpected exception
    operator: bool           # stopped by the operator (botctl stop/kill)
    seconds: float           # how long the session ran


def decide(outcome, logged_in):
    """What to do after a session: "restart", or go idle with a reason
    ("idle_finished", "idle_giving_up", "idle_operator")."""
    if outcome.operator or outcome.final == "interrupted":
        return "idle_operator"
    if outcome.crashed:
        return "restart"
    if outcome.final == "done":
        return "idle_finished"
    # stopped by the bot itself: a logout explains it, otherwise a human is needed
    return "idle_giving_up" if logged_in else "restart"


class Backoff:
    """30 s, 60 s, 120 s ... capped at 600 s; reset by a long session or reset()."""

    def __init__(self):
        self._next = BACKOFF_START

    def next(self):
        delay = self._next
        self._next = min(self._next * 2, BACKOFF_MAX)
        return delay

    def reset(self):
        self._next = BACKOFF_START

    def session_ran(self, seconds):
        if seconds >= LONG_SESSION:
            self.reset()


class Budget:
    """At most BUDGET automatic restarts per rolling BUDGET_WINDOW seconds."""

    def __init__(self, now_fn):
        self._now = now_fn
        self._times = deque()

    def allow(self):
        now = self._now()
        while self._times and now - self._times[0] > BUDGET_WINDOW:
            self._times.popleft()
        if len(self._times) >= BUDGET:
            return False
        self._times.append(now)
        return True

    def reset(self):
        self._times.clear()
