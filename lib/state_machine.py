"""
Shared bot runner — drives a transitions-backed session model.

Each bot declares its states + transition table (bot/states.py) and a dict of
handlers {state: callable}. A handler does one step of real work and returns
an event name ("ok", "fail", ...); the transition table decides where that
event leads. This loop owns the parts every bot repeats: the O-pause gate
before each step, the overlay's step label, and the soft-stop check.
"""
import time

from transitions import MachineError

import lib.events as events
import lib.pause as pause


def run_machine(model, handlers, stats, final_states, cycle_start=None):
    """
    Run until model.state is in final_states; returns that state's name.

    Soft stop (overlay Stop, stats["stop"]) only fires when the model is about
    to run a cycle_start state (one name or a collection), so a trip in progress
    always finishes — the bot's table must declare a "stop" trigger from each.
    ForceStop (P) is not caught.
    stats["step"] is left naming the last state whose handler ran.
    Emits step / pause / soft_stop events to the session's event log, if any.
    An event whose every row is blocked by its conditions raises MachineError
    (transitions itself would silently stay put and re-run the same handler).
    """
    if isinstance(cycle_start, str):
        cycle_start = {cycle_start}
    cycle_start = cycle_start or set()
    log = events.current()
    while model.state not in final_states:
        gate_pause(model.state)   # before the stop check, so Stop clicked while paused is honoured
        if model.state in cycle_start and stats.get("stop"):
            if log:
                log.emit("soft_stop", state=model.state)
            model.trigger("stop")
            continue
        stats["step"] = state = model.state
        started = time.time()
        event = handlers[state]()
        if log:
            log.emit("step", state=state, result=event, seconds=round(time.time() - started, 3),
                     run=stats.get("run"))
        if not model.trigger(event):
            raise MachineError(f"no transition for {event!r} from {model.state!r} "
                               f"(all conditions failed)")
    return model.state


def gate_pause(state):
    """pause.wait(), recording how long it blocked in the session's event log —
    including a pause that ends in a force stop (P/End pressed while paused)."""
    started, blocked = time.time(), False
    try:
        blocked = pause.wait()
    except pause.ForceStop:
        blocked = pause.is_paused()
        raise
    finally:
        log = events.current()
        if blocked and log:
            seconds = time.time() - started
            log.paused_seconds += seconds
            log.emit("pause", state=state, seconds=round(seconds, 3))


def ok_or_fail(result):
    """Map a truthy/falsy action result to the standard "ok"/"fail" events."""
    return "ok" if result else "fail"
