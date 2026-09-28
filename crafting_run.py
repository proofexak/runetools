"""
Crafting Bot (Path of Exile) — standalone launcher, independent of the OSRS
bot suite in run.py.
"""
import threading, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib.pause as pause
import lib.overlay as overlay
from lib.overlay import start as start_overlay
import crafting.run as crafting_run

pause.setup("p", stop_key="end")

stats     = {"run": 0, "step": "starting", "start": None, "stop": False}
_selected = threading.Event()


def _open_crafting_editor():
    from crafting.config_editor import open_editor
    open_editor()


def _log_done_checks():
    from crafting.crafting import log_all_done_checks
    log_all_done_checks()


MENU = [
    ("Start Crafting", "start", "#1a3a1a", "#2d6a2d", ("⚙", _open_crafting_editor)),
    ("Log Done Checks", _log_done_checks, "#1a2a3a", "#2a4a6a"),
    ("Exit", lambda: os._exit(0), "#550000", "#881111"),
]

start_overlay(
    stats         = stats,
    hide_selected = _selected,
    use_selector  = True,
    menu          = MENU,
    on_select     = lambda v: None,
    stats_extra   = lambda s: f"Items:   {s['run']}",
    corner        = "top-right",
)

# ── Session loop ───────────────────────────────────────────────────────────────

while True:
    _selected.wait()
    crafting_run.run(stats)
    _selected = threading.Event()
    overlay.show_selector(_selected)
