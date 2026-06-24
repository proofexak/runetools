"""
Tanner bot config editor — defines fields and wires up the generic lib editor.
"""
import threading, re, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tanner.config as cfg
from lib.config_editor import run_editor

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.py")

FIELDS = [
    # (section, label, attr, ftype)
    # types: "point"        → (x, y)
    #        "point_color"  → (x, y, (r,g,b))
    #        "region"       → (left, top, width, height)  or  [(x,y), ...]
    ("Navigation",  "Compass",          "COMPASS",              "point"),
    ("Navigation",  "Character",        "CHARACTER",            "point"),
    ("Navigation",  "Tanner Area",      "TANNER_AREA",          "region"),
    ("Navigation",  "Ellis Region",     "ELLIS_REGION",         "region"),
    ("Bank",        "Bank Check",       "BANK_CHECK",           "point_color"),
    ("Bank",        "Inventory Check",  "INVENTORY_CHECK",      "point_color"),
    ("Bank",        "Deposit Button",   "DEPOSIT_BTN",          "point"),
    ("Bank",        "Hide Slot",        "HIDE_SLOT",            "point"),
    ("Bank",        "Bank Slot 2",      "BANK_SLOT_2",          "point"),
    ("Bank",        "Bank Region",      "BANK_REGION",          "region"),
    ("Tanning",     "Tanning Check",    "TANNING_CHECK",        "point_color"),
    ("Interface",   "Green Dragonhide", "IB:green dragonhide",  "point_color"),
    ("Interface",   "Blue Dragonhide",  "IB:blue dragonhide",   "point_color"),
    ("Interface",   "Red Dragonhide",   "IB:red dragonhide",    "point_color"),
    ("Interface",   "Black Dragonhide", "IB:black dragonhide",  "point_color"),
    ("Movement",    "Movement Region",  "MOVEMENT_REGION",      "region"),
]

REGION_COLORS = {
    "TANNER_AREA":    "#ff8800",
    "ELLIS_REGION":   "#00ccff",
    "BANK_REGION":    "#ff44cc",
    "MOVEMENT_REGION":"#ffff00",
}


# ── Value helpers ─────────────────────────────────────────────────────────────

def _get(attr):
    if attr.startswith("IB:"):
        return cfg.INTERFACE_BUTTONS.get(attr[3:])
    return getattr(cfg, attr, None)


def _apply(attr, val):
    if attr.startswith("IB:"):
        cfg.INTERFACE_BUTTONS[attr[3:]] = val
    else:
        setattr(cfg, attr, val)


def _save(attr, val):
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    if attr.startswith("IB:"):
        hide = attr[3:]
        x, y, (r, g, b) = val
        new_val = f"({x}, {y}, ({r}, {g}, {b}))"
        pattern = rf'("{re.escape(hide)}":\s*)(\([^(]+\([^)]+\)[^)]*\))'
        content = re.sub(pattern, rf'\g<1>{new_val}', content)
    else:
        pattern = rf'^({re.escape(attr)}\s*=\s*).*$'
        content = re.sub(pattern, rf'\g<1>{repr(val)}', content, flags=re.MULTILINE)

    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        f.write(content)


# ── Entry point ───────────────────────────────────────────────────────────────

def open_editor():
    threading.Thread(daemon=True, target=run_editor, args=(
        "Tanner Config", FIELDS, _get, _apply, _save,
    ), kwargs=dict(region_colors=REGION_COLORS)).start()
