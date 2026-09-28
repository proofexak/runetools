"""
Mining descriptor for the overlay menu (see lib/bots.py). Sub-bots live in
miner/<name>/; Varrock Exp gets a launch here once it exists (PRO-7).
"""
from lib.bots import Bot, Launch


def _golden_nuggets(stats):
    from miner.golden_nuggets.run import run
    run(stats)


def _configure():
    from miner.golden_nuggets.config_editor import open_editor
    open_editor()


BOT = Bot(
    name       = "Mining",
    order      = 20,
    colors     = ("#2a1a0a", "#4a3010"),
    launches   = [Launch("Golden Nuggets", _golden_nuggets, ("#4a3a00", "#7a6200"))],
    configure  = _configure,
    stats_line = lambda s: f"Ores:    {s['run']}",
)
