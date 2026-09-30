"""
OSRS Bot — main menu overlay.
Bots are discovered from their bot.py descriptors (lib/bots.py); picking one
runs its session here, then the menu comes back.
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

pause.setup(pause_hotkey="o", stop_hotkey="p")

stats     = {"run": 0, "step": "starting", "start": None, "stop": False}
_selected = threading.Event()
_pending  = {"bot": None, "start": None}

# ── Menu callbacks ─────────────────────────────────────────────────────────────

def _begin(bot, start):
    """Hand a session to the main loop below and switch the overlay to stats."""
    _pending["bot"], _pending["start"] = bot, start
    overlay.switch_to_stats()
    _selected.set()


def _ask_int(prompt, on_value):
    import tkinter as tk

    dlg = tk.Toplevel()
    dlg.title("RuneTools")
    dlg.configure(bg="#0f0f1e")
    dlg.geometry("260x110+300+300")
    dlg.wm_attributes("-topmost", True)

    tk.Label(dlg, text=prompt, bg="#0f0f1e", fg="#ccccee", font=("Consolas", 9)
             ).pack(padx=10, pady=(12, 4))

    ent = tk.Entry(dlg, bg="#1a1a33", fg="#ccccee", font=("Consolas", 9),
                   insertbackground="#ccccee")
    ent.pack(padx=10, pady=4, fill="x")
    ent.focus_set()

    def _submit():
        try:
            value = int(ent.get())
        except ValueError:
            return
        dlg.destroy()
        on_value(value)

    ent.bind("<Return>", lambda e: _submit())
    tk.Button(dlg, text="Start", command=_submit,
              bg="#1a3322", fg="#00ff88", font=("Consolas", 9),
              relief="flat", padx=12).pack(pady=(6, 8))


def _open_ge_editor():
    from lib.ge_config_editor import open_ge_editor
    open_ge_editor()


def _open_energy_editor():
    from lib.energy_config_editor import open_energy_editor
    open_energy_editor()


def _stats_extra(s):
    bot = _pending["bot"]
    return bot.stats_line(s) if bot and bot.stats_line else None


MENU = build_menu(
    discover(ROOT),
    begin   = _begin,
    ask_int = _ask_int,
    tools   = [("⚙ GE Config", _open_ge_editor), ("⚙ Energy Config", _open_energy_editor)],
)

start_overlay(
    stats         = stats,
    hide_selected = _selected,
    use_selector  = True,
    menu          = MENU,
    on_select     = lambda value: None,   # every menu entry is a callable now
    stats_extra   = _stats_extra,
)

# ── Session loop ───────────────────────────────────────────────────────────────

while True:
    _selected.wait()
    run_guarded(_pending["start"], stats, bot=_pending["bot"].name)
    _pending["bot"] = _pending["start"] = None
    _selected = threading.Event()
    overlay.show_selector(_selected)
