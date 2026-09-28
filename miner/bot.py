"""
Mining descriptor for the overlay menu (see lib/bots.py). Each sub-bot in
miner/<name>/ is one launch with its own ⚙ editor button.
"""
from lib.bots import Bot, Launch


def _varrock_exp(stats):
    from miner.varrock_exp.run import run
    run(stats)


def _configure_varrock_exp():
    from miner.varrock_exp.config_editor import open_editor
    open_editor()


def _golden_nuggets(stats):
    from miner.golden_nuggets.run import run
    run(stats)


def _configure_golden_nuggets():
    from miner.golden_nuggets.config_editor import open_editor
    open_editor()


BOT = Bot(
    name       = "Mining",
    order      = 20,
    colors     = ("#2a1a0a", "#4a3010"),
    launches   = [
        Launch("Varrock Exp",    _varrock_exp,    ("#3a2a0a", "#6a4a15"), configure=_configure_varrock_exp),
        Launch("Golden Nuggets", _golden_nuggets, ("#4a3a00", "#7a6200"), configure=_configure_golden_nuggets),
    ],
    stats_line = lambda s: f"Ores:    {s['run']}",
)
