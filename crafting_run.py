"""
Crafting Bot (Path of Exile) — standalone launcher, independent of the OSRS
bot suite in run.py. Lists the "poe" suite bots (lib/bots.py) in a flat menu;
P pauses, End force-stops, overlay sits top-right.
"""
import threading, os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import lib.events as events
events.install_excepthooks()   # first: even import errors below get recorded

import lib.pause as pause
import lib.overlay as overlay
from lib.overlay import start as start_overlay
from lib.bots import discover, build_menu, run_guarded

pause.setup(pause_hotkey="p", stop_hotkey=None, stop_key="end")

stats     = {"run": 0, "step": "starting", "start": None, "stop": False}
_selected = threading.Event()
_pending  = {"bot": None, "start": None}


def _begin(bot, start):
    _pending["bot"], _pending["start"] = bot, start
    overlay.switch_to_stats()
    _selected.set()


def _log_done_checks():
    from crafting.actions import log_all_done_checks
    log_all_done_checks()


def _stats_extra(s):
    bot = _pending["bot"]
    return bot.stats_line(s) if bot and bot.stats_line else None


MENU = build_menu(
    discover(ROOT, suite="poe"),
    begin   = _begin,
    ask_int = None,              # no PoE launch asks for a number
    tools   = [("Log Done Checks", _log_done_checks)],
    flat    = True,
)

start_overlay(
    stats         = stats,
    hide_selected = _selected,
    use_selector  = True,
    menu          = MENU,
    on_select     = lambda value: None,
    stats_extra   = _stats_extra,
    corner        = "top-right",
)

# ── Session loop ───────────────────────────────────────────────────────────────

while True:
    _selected.wait()
    run_guarded(_pending["start"], stats, bot=_pending["bot"].name)
    _pending["bot"] = _pending["start"] = None
    _selected = threading.Event()
    overlay.show_selector(_selected)
