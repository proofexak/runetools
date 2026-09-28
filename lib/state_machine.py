"""
Shared bot runner — drives a transitions-backed session model.

Each bot declares its states + transition table (bot/states.py) and a dict of
handlers {state: callable}. A handler does one step of real work and returns
an event name ("ok", "fail", ...); the transition table decides where that
event leads. This loop owns the parts every bot repeats: the O-pause gate
before each step, the overlay's step label, and the soft-stop check.
"""
from transitions import MachineError

import lib.pause as pause


def run_machine(model, handlers, stats, final_states, cycle_start=None):
    """
    Run until model.state is in final_states; returns that state's name.

    Soft stop (overlay Stop, stats["stop"]) only fires when the model is about
    to run cycle_start, so a trip in progress always finishes — the bot's table
    must declare a "stop" trigger from cycle_start. ForceStop (P) is not caught.
    stats["step"] is left naming the last state whose handler ran.
    An event whose every row is blocked by its conditions raises MachineError
    (transitions itself would silently stay put and re-run the same handler).
    """
    while model.state not in final_states:
        pause.wait()   # before the stop check, so Stop clicked while paused is honoured
        if model.state == cycle_start and stats.get("stop"):
            model.trigger("stop")
            continue
        stats["step"] = model.state
        event = handlers[model.state]()
        if not model.trigger(event):
            raise MachineError(f"no transition for {event!r} from {model.state!r} "
                               f"(all conditions failed)")
    return model.state


def ok_or_fail(result):
    """Map a truthy/falsy action result to the standard "ok"/"fail" events."""
    return "ok" if result else "fail"
