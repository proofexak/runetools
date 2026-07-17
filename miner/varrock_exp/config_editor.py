"""
Varrock Exp config editor.
"""
import threading, re, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
import miner.varrock_exp.config as cfg
from lib.config_editor import run_editor

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.py")

FIELDS = [
    ("Navigation", "Compass",         "COMPASS",        "point"),
    ("Mining",     "Rock Region",     "ROCK_REGION",    "region"),
    ("Mining",     "Ore Slot",        "ORE_SLOT",       "point"),
    ("Mining",     "Slot Background", "SLOT_BG_COLOR",  "point_color"),
]

REGION_COLORS = {
    "ROCK_REGION": "#ff44cc",
}


def _get(attr):
    return getattr(cfg, attr, None)


def _apply(attr, val):
    setattr(cfg, attr, val)


def _save(attr, val):
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    pattern = rf'^({re.escape(attr)}\s*=\s*).*$'
    content = re.sub(pattern, rf'\g<1>{repr(val)}', content, flags=re.MULTILINE)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        f.write(content)


def open_editor():
    threading.Thread(daemon=True, target=run_editor, args=(
        "Varrock Exp Config", FIELDS, _get, _apply, _save,
    ), kwargs=dict(region_colors=REGION_COLORS)).start()
