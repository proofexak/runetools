import pytest

from lib import supervisor as sv
from lib.supervisor import Outcome, decide, Budget, Backoff


def out(final="stopped", reason=None, crashed=False, operator=False, seconds=60.0):
    return Outcome(final=final, reason=reason, crashed=crashed, operator=operator, seconds=seconds)


@pytest.mark.parametrize("outcome,logged_in,action", [
    (out(final="crashed", crashed=True), True, "restart"),
    (out(final="crashed", crashed=True), False, "restart"),
    (out(reason="recovery failed"), False, "restart"),            # logout explains the failure
    (out(reason="recovery failed"), True, "idle_giving_up"),      # real problem
    (out(final="done", reason="out of hides, GE restock disabled"), True, "idle_finished"),
    (out(final="done"), False, "idle_finished"),
    (out(operator=True), True, "idle_operator"),
    (out(final="crashed", crashed=True, operator=True), True, "idle_operator"),   # operator wins
    (out(final="interrupted"), True, "idle_operator"),
])
def test_decide(outcome, logged_in, action):
    assert decide(outcome, logged_in) == action


def test_constants():
    assert (sv.BACKOFF_START, sv.BACKOFF_MAX, sv.LONG_SESSION) == (30, 600, 600)
    assert (sv.BUDGET, sv.BUDGET_WINDOW, sv.MAX_LOGIN_FAILURES, sv.CREDENTIALS_RECHECK) == (5, 3600, 3, 60)


def test_backoff_doubles_to_cap():
    b = Backoff()
    assert [b.next() for _ in range(7)] == [30, 60, 120, 240, 480, 600, 600]


def test_backoff_resets_after_a_long_session():
    b = Backoff()
    b.next(); b.next()
    b.session_ran(599)
    assert b.next() == 120
    b.session_ran(600)
    assert b.next() == 30


def test_backoff_reset():
    b = Backoff()
    b.next(); b.next()
    b.reset()
    assert b.next() == 30


def test_budget_allows_five_per_rolling_hour():
    now = [0.0]
    budget = Budget(lambda: now[0])
    for i in range(5):
        now[0] = i * 60
        assert budget.allow() is True
    now[0] = 600
    assert budget.allow() is False            # 6th inside the hour
    now[0] = 3601                             # oldest (t=0) is now > 3600 s old
    assert budget.allow() is True
    budget.reset()
    assert all(budget.allow() for _ in range(5))


@pytest.mark.parametrize("outcome,logged_in,block_over,action", [
    (out(final="stopped"), True, True, "next_block"),              # soft stop at the block's end
    (out(final="crashed", crashed=True), True, True, "next_block"), # no restart after the block
    (out(operator=True), True, True, "idle_operator"),             # botctl stop / kill still win
    (out(final="interrupted"), True, True, "idle_operator"),
    (out(final="done"), True, False, "skip_block"),                # finished: sit out the rest
    (out(final="crashed", crashed=True), True, False, "restart"),
    (out(reason="recovery failed"), False, False, "restart"),
    (out(reason="recovery failed"), True, False, "give_up_block"),   # this block is lost, not every later one
])
def test_schedule_decide(outcome, logged_in, block_over, action):
    assert sv.schedule_decide(outcome, logged_in, block_over) == action


def test_schedule_constants():
    assert (sv.SCHEDULE_RECHECK, sv.BLOCK_FORCE_GRACE, sv.MAX_BLOCK_GIVE_UPS) == (60, 1200, 3)
