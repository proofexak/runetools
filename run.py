"""
OSRS Bot — main menu overlay.
Handles bot/hide selection; runs the chosen session; loops back to menu.
"""
import threading, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib.pause as pause
import lib.overlay as overlay
from lib.overlay import start as start_overlay

pause.setup(pause_hotkey="o", stop_hotkey="p")

stats     = {"run": 0, "step": "starting", "start": None, "stop": False}
_selected = threading.Event()
_pending  = {"bot": None, "from_ge": False, "choc_count": None}

# ── Lazy editor openers ────────────────────────────────────────────────────────

def _open_tanner_editor():
    from tanner.config_editor import open_editor
    open_editor()

def _open_varrock_exp_editor():
    from miner.varrock_exp.config_editor import open_editor
    open_editor()

def _open_golden_nuggets_editor():
    from miner.golden_nuggets.config_editor import open_editor
    open_editor()

def _open_ge_editor():
    from lib.ge_config_editor import open_ge_editor
    open_ge_editor()

def _open_energy_editor():
    from lib.energy_config_editor import open_energy_editor
    open_energy_editor()

def _open_choc_editor():
    from choc.config_editor import open_editor
    open_editor()

# ── Chocolate run popup ─────────────────────────────────────────────────────────

def _open_choc_run_popup():
    import tkinter as tk

    dlg = tk.Toplevel()
    dlg.title("Chocolate Grind")
    dlg.configure(bg="#0f0f1e")
    dlg.geometry("260x110+300+300")
    dlg.wm_attributes("-topmost", True)

    tk.Label(dlg, text="How many chocolate bars do you have?",
             bg="#0f0f1e", fg="#ccccee", font=("Consolas", 9)
             ).pack(padx=10, pady=(12, 4))

    ent = tk.Entry(dlg, bg="#1a1a33", fg="#ccccee", font=("Consolas", 9),
                   insertbackground="#ccccee")
    ent.pack(padx=10, pady=4, fill="x")
    ent.focus_set()

    def _submit():
        try:
            count = int(ent.get())
        except ValueError:
            return
        dlg.destroy()
        _pending["bot"]        = "choc"
        _pending["choc_count"] = count
        overlay.switch_to_stats()
        _selected.set()

    ent.bind("<Return>", lambda e: _submit())
    tk.Button(dlg, text="Start", command=_submit,
              bg="#1a3322", fg="#00ff88", font=("Consolas", 9),
              relief="flat", padx=12).pack(pady=(6, 8))

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
        ("Varrock Exp",      "varrock exp",              "#3a2a0a", "#6a4a15"),
        ("⚙ Configure",     _open_varrock_exp_editor,   "#1a1a33", "#2a2a55"),
        ("Golden Nuggets",   "golden nuggets",           "#4a3a00", "#7a6200"),
        ("⚙ Configure",     _open_golden_nuggets_editor,"#1a1a33", "#2a2a55"),
    ], "#2a1a0a", "#4a3010"),
    ("Choco Grind", [
        ("⚙ Configure", _open_choc_editor,     "#1a1a33", "#2a2a55"),
        ("Run",          _open_choc_run_popup, "#4a2a00", "#7a5010"),
    ], "#3a2a1a", "#6a4a2d"),
    ("⚙ GE Config", _open_ge_editor, "#1a1a33", "#2a2a55"),
    ("⚙ Energy Config", _open_energy_editor, "#1a1a33", "#2a2a55"),
    ("Exit", lambda: os._exit(0), "#550000", "#881111"),
]

_TANNER_HIDES = {"green dragonhide", "blue dragonhide", "red dragonhide", "black dragonhide"}

def _on_select(value):
    if value in _TANNER_HIDES:
        import tanner.config as tanner_cfg
        tanner_cfg.HIDE_TYPE = value
        _pending["bot"]      = "tanner"
        _pending["from_ge"]  = False
    elif value in {"varrock exp", "golden nuggets"}:
        import miner.config as miner_cfg
        miner_cfg.LOCATION = value
        _pending["bot"]    = "miner"

def _stats_extra(s):
    if _pending["bot"] == "miner":
        return f"Ores:    {s['run']}"
    if _pending["bot"] == "choc":
        import choc.config as choc_cfg
        return f"Ground:  {s['run'] * choc_cfg.GRIND_COUNT}"
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
    elif _pending["bot"] == "choc":
        import choc.run as choc_run
        choc_run.run(stats, _pending["choc_count"])

    _pending["bot"]        = None
    _pending["from_ge"]    = False
    _pending["choc_count"] = None
    _selected = threading.Event()
    overlay.show_selector(_selected)
