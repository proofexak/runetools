"""
Crafting (Path of Exile) descriptor — suite "poe", so it's listed by
crafting_run.py's launcher and never by the OSRS menu (see lib/bots.py).
"""
from lib.bots import Bot, Launch


def _start(stats):
    from crafting.run import run
    run(stats)


def _configure():
    from crafting.config_editor import open_editor
    open_editor()


BOT = Bot(
    name       = "Crafting",
    suite      = "poe",
    launches   = [Launch("Start Crafting", _start, ("#1a3a1a", "#2d6a2d"), configure=_configure)],
    stats_line = lambda s: f"Items:   {s['run']}",
)
