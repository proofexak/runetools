"""
Chocolate grind descriptor for the overlay menu (see lib/bots.py).
"""
from lib.bots import Bot, Launch


def _start(stats, count):
    from choc.run import run
    run(stats, count)


def _configure():
    from choc.config_editor import open_editor
    open_editor()


def _stats_line(s):
    import choc.config as config
    return f"Ground:  {s['run'] * config.GRIND_COUNT}"


BOT = Bot(
    name       = "Choco Grind",
    order      = 30,
    colors     = ("#3a2a1a", "#6a4a2d"),
    launches   = [Launch("Run", _start, ("#4a2a00", "#7a5010"),
                         ask_int="How many chocolate bars do you have?")],
    configure  = _configure,
    stats_line = _stats_line,
)
