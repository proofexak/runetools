"""
Standard bot session lifecycle — every bot's run() delegates here.

    log → reset pause/stats → build session model → 3s countdown →
    [pause gate → setup → run_machine] → summary

P pressed during the countdown or setup ends the session cleanly; the model is
built before the countdown (building it has no in-game side effects) so the
summary always has one.
"""
import time

import lib.log as log
import lib.pause as pause
from lib.state_machine import run_machine


def format_elapsed(seconds):
    h, rem = divmod(int(seconds), 3600)
    m, s   = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def run_session(stats, *, log_prefix, intro, setup, session, handlers,
                final_states, cycle_start, summary, game="OSRS", teardown=None):
    """
    log_prefix — path prefix for the session log file
    intro      — lines printed before the countdown
    setup()    — one-time in-game setup after the countdown (e.g. camera)
    session()  — builds the transitions-backed model
    handlers(model) -> {state: handler}
    summary(model, final, last_step) -> str, printed in the closing line
    game       — named in the "switch to ..." hint
    teardown() — always runs after the machine stops, even on a crash
                 (e.g. release a held key); the crash still propagates
    Returns the final state ("stopped" on ForceStop).
    """
    log.setup(log_prefix)
    for line in intro:
        print(line)
    print(f"Starting in 3s — switch to {game}. {pause.hint()}")

    pause.reset()
    stats.update({"run": 0, "step": "starting", "start": None, "stop": False})
    model = session()
    time.sleep(3)

    start = time.time()
    try:
        pause.wait()
        setup()
        stats["start"] = start = time.time()
        final = run_machine(model, handlers(model), stats, final_states, cycle_start)
    except pause.ForceStop:
        print("Force stopped via overlay.")
        final = "stopped"
    finally:
        if teardown:
            teardown()

    last_step = stats["step"]
    stats["step"] = final
    print(f"Session ended ({final} after {last_step}). {summary(model, final, last_step)} | "
          f"Time: {format_elapsed(time.time() - start)}")
    return final
