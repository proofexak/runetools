"""
Golden Nuggets config editor.
"""
import threading, re, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
import miner.golden_nuggets.config as cfg
from lib.config_editor import run_editor

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.py")

FIELDS = [
    ("Navigation", "Compass",          "COMPASS",          "point"),
    ("Navigation", "Character",        "CHARACTER",        "point"),
    ("Navigation", "Movement Region",  "MOVEMENT_REGION",  "region"),
    ("Mining",     "Pay-dirt Region",  "PAY_DIRT_REGION",  "region"),
    ("Mining",     "Hopper Region",    "HOPPER_REGION",    "region"),
    ("Mining",     "Strut Region",      "STRUT_REGION",      "region"),
    ("Mining",     "Strut Near Region","STRUT_NEAR_REGION", "region"),
    ("Sack & Bank","Sack Region",      "SACK_REGION",      "region"),
    ("Sack & Bank","Sack (Bank) Rgn",  "SACK_BANK_REGION", "region"),
    ("Sack & Bank","Bank Region",      "BANK_REGION",      "region"),
    ("Sack & Bank","Bank Check Pixel", "BANK_CHECK",       "point_color"),
    ("Sack & Bank","Deposit All Btn",  "DEPOSIT_ALL_BTN",  "point"),
    ("Inventory",  "Slot Anchors",     "INV_ANCHORS",      "inv_anchor"),
    ("Inventory",  "Empty Slot Color", "SLOT_BG_COLOR",    "point_color"),
]

REGION_COLORS = {
    "PAY_DIRT_REGION": "#ff44cc",
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
        "Golden Nuggets Config", FIELDS, _get, _apply, _save,
    ), kwargs=dict(region_colors=REGION_COLORS)).start()
