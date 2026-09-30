"""
Standard bot session lifecycle — every bot's run() delegates here.

    log → reset pause/stats → build session model → 3s countdown →
    [pause gate → setup → run_machine] → summary

P pressed during the countdown or setup ends the session cleanly; the model is
built before the countdown (building it has no in-game side effects) so the
summary always has one.
"""
import os, time

import lib.events as events
import lib.log as log
import lib.pause as pause
from lib.state_machine import run_machine, gate_pause

_active_teardown = [None]   # the running session's teardown, for emergency_teardown()


def emergency_teardown():
    """Run the active session's teardown now (once) — for the overlay's Exit
    button, which ends the process without unwinding the session."""
    fn, _active_teardown[0] = _active_teardown[0], None
    if fn:
        fn()


def format_elapsed(seconds):
    h, rem = divmod(int(seconds), 3600)
    m, s   = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def run_session(stats, *, bot, log_prefix, intro, setup, session, handlers,
                final_states, cycle_start, summary, params=None, game="OSRS", teardown=None):
    """
    bot        — bot name recorded in the event log (e.g. "tanner")
    params     — JSON-able session parameters recorded in session_start
    log_prefix — path prefix for the session's .log and .jsonl files
    intro      — lines printed before the countdown
    setup()    — one-time in-game setup after the countdown (e.g. camera)
    session()  — builds the transitions-backed model
    handlers(model) -> {state: handler}
    summary(model, final, last_step) -> str, printed in the closing line
    game       — named in the "switch to ..." hint
    teardown() — always runs after the machine stops, even on a crash
                 (e.g. release a held key); the crash still propagates
    Returns the final state ("stopped" on ForceStop). Any other exception is
    written to the event log (error + session_end "crashed"/"interrupted") and
    re-raised.
    """
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log.setup(log_prefix, stamp=stamp)
    ev = events.start(f"{log_prefix}_{stamp}.jsonl", bot, stamp)
    ev.emit("session_start", params=params or {}, pid=os.getpid())
    began = start = time.time()
    stats.update({"run": 0, "step": "starting", "start": None, "stop": False})
    model, final, error = None, None, None
    try:
        for line in intro:
            print(line)
        print(f"Starting in 3s — switch to {game}. {pause.hint()}")
        pause.reset()
        _active_teardown[0] = teardown
        model = session()
        time.sleep(3)
        gate_pause("starting")
        setup()
        stats["start"] = start = time.time()
        final = run_machine(model, handlers(model), stats, final_states, cycle_start)
    except pause.ForceStop:
        print("Force stopped via overlay.")
        ev.emit("force_stop", state=stats.get("step"))
        final = "stopped"
    except BaseException as e:
        error = e
        final = "interrupted" if isinstance(e, KeyboardInterrupt) else "crashed"
        ev.emit("error", where="session", state=stats.get("step"), **events.error_fields(e))
    try:
        emergency_teardown()   # single-shot: skipped if Exit already ran it
    except BaseException as e:
        ev.emit("error", where="teardown", state=stats.get("step"), **events.error_fields(e))
        if error is None:
            error, final = e, "crashed"

    last_step = stats["step"]
    stats["step"] = final
    ended = time.time()
    ev.emit("session_end", final=final, reason=getattr(model, "stop_reason", None),
            last_step=last_step, stats=dict(stats),
            active_seconds=round(ended - began - ev.paused_seconds, 3),
            paused_seconds=round(ev.paused_seconds, 3))
    events.finish()
    if error is not None:
        events.mark_logged(error)
        raise error
    print(f"Session ended ({final} after {last_step}). {summary(model, final, last_step)} | "
          f"Time: {format_elapsed(ended - start)}")
    return final
