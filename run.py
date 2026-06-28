"""
OSRS Bot — main menu overlay.
Handles bot/hide selection; runs the chosen session; loops back to menu.
"""
import threading, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib.pause as pause
import lib.overlay as overlay
from lib.overlay import start as start_overlay

pause.setup("p")

stats     = {"run": 0, "step": "starting", "start": None, "stop": False}
_selected = threading.Event()
_pending  = {"bot": None, "from_ge": False}

# ── Lazy editor openers ────────────────────────────────────────────────────────

def _open_tanner_editor():
    from tanner.config_editor import open_editor
    open_editor()

def _open_miner_editor():
    from miner.config_editor import open_editor
    open_editor()

def _open_ge_editor():
    from lib.ge_config_editor import open_ge_editor
    open_ge_editor()

# ── GE button helpers ──────────────────────────────────────────────────────────

def _select_from_ge(value):
    import tanner.config as tanner_cfg
    tanner_cfg.HIDE_TYPE = value
    _pending["bot"]      = "tanner"
    _pending["from_ge"]  = True
    overlay.switch_to_stats()
    _selected.set()

def _ge_btn(value):
    return ("GE", lambda v=value: _select_from_ge(v))

# ── Menu ───────────────────────────────────────────────────────────────────────

MENU = [
    ("Tanning", [
        ("Green Dragonhide", "green dragonhide", "#1a4a1a", "#2d7a2d", _ge_btn("green dragonhide")),
        ("Blue Dragonhide",  "blue dragonhide",  "#0d2444", "#1a4a88", _ge_btn("blue dragonhide")),
        ("Red Dragonhide",   "red dragonhide",   "#440d0d", "#882020", _ge_btn("red dragonhide")),
        ("Black Dragonhide", "black dragonhide", "#1a1a1a", "#333333", _ge_btn("black dragonhide")),
        ("⚙ Configure",      _open_tanner_editor, "#1a1a33", "#2a2a55"),
    ], "#1a3a1a", "#2d6a2d"),
    ("Mining", [
        ("Varrock Exp", "varrock exp", "#3a2a0a", "#6a4a15"),
        ("⚙ Configure",   _open_miner_editor, "#1a1a33", "#2a2a55"),
    ], "#2a1a0a", "#4a3010"),
    ("⚙ GE Config", _open_ge_editor, "#1a1a33", "#2a2a55"),
    ("Exit", lambda: os._exit(0), "#550000", "#881111"),
]

_TANNER_HIDES = {"green dragonhide", "blue dragonhide", "red dragonhide", "black dragonhide"}

def _on_select(value):
    if value in _TANNER_HIDES:
        import tanner.config as tanner_cfg
        tanner_cfg.HIDE_TYPE = value
        _pending["bot"]      = "tanner"
        _pending["from_ge"]  = False
    elif value == "varrock exp":
        import miner.config as miner_cfg
        miner_cfg.LOCATION = value
        _pending["bot"]    = "miner"

def _stats_extra(s):
    if _pending["bot"] == "miner":
        return f"Ores:    {s['run']}"
    return f"Hides:   {s['run'] * 27}"

start_overlay(
    stats         = stats,
    hide_selected = _selected,
    use_selector  = True,
    menu          = MENU,
    on_select     = _on_select,
    stats_extra   = _stats_extra,
)

# ── Session loop ───────────────────────────────────────────────────────────────

while True:
    _selected.wait()

    if _pending["bot"] == "tanner":
        import tanner.run as tanner_run
        tanner_run.run(stats, start_from_ge=_pending["from_ge"])
    elif _pending["bot"] == "miner":
        import miner.run as miner_run
        miner_run.run(stats)

    _pending["bot"]     = None
    _pending["from_ge"] = False
    _selected = threading.Event()
    overlay.show_selector(_selected)
