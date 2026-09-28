"""
Miner bot config editor — defines fields and wires up the generic lib editor.
"""
import threading, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import miner.config as cfg
from lib.config_editor import run_editor, save_attr

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.py")

FIELDS = [
    # (section, label, attr, ftype)
    ("Navigation", "Compass",          "COMPASS",        "point"),
    ("Mining",     "Rock Region",      "ROCK_REGION",    "region"),
    ("Mining",     "Ore Slot",      "ORE_SLOT",    "point"),
    ("Mining",     "Slot Background",  "SLOT_BG_COLOR",  "point_color"),
]

REGION_COLORS = {
    "ROCK_REGION": "#ff44cc",
}


def _get(attr):
    return getattr(cfg, attr, None)


def _apply(attr, val):
    setattr(cfg, attr, val)


def _save(attr, val):
    save_attr(CONFIG_PATH, attr, val)


def open_editor():
    threading.Thread(daemon=True, target=run_editor, args=(
        "Miner Config", FIELDS, _get, _apply, _save,
    ), kwargs=dict(region_colors=REGION_COLORS)).start()
