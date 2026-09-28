"""
Energy config editor — defines fields and wires up the generic lib editor.
"""
import threading, os, sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import lib.energy_config as cfg
from lib.config_editor import run_editor, save_attr

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "energy_config.py")

FIELDS = [
    ("Energy",   "Energy Region",       "ENERGY_REGION",       "region"),
    ("Stamina",  "Stamina Potion Slot", "STAMINA_POTION_SLOT", "point"),
    ("Stamina",  "Drink Threshold",     "DRINK_THRESHOLD",     "number"),
    ("Bank",     "Bank Check",          "BANK_CHECK",          "point_color"),
    ("Bank",     "Deposit All",         "DEPOSIT_BTN",         "point"),
    ("Bank",     "Potion Tab",          "POTION_TAB",          "point"),
    ("Bank",     "Bank Slot 1",         "BANK_SLOT_1",         "point"),
    ("Bank",     "Inventory Check",     "INVENTORY_CHECK",     "point_color"),
    ("Bank",     "Bank Booth Region",   "BANK_BOOTH_REGION",   "region"),
]

REGION_COLORS = {
    "ENERGY_REGION":     "#ffaa00",
    "BANK_BOOTH_REGION": "#ff00ff",
}


def _get(attr):
    return getattr(cfg, attr, None)


def _apply(attr, val):
    setattr(cfg, attr, val)


def _save(attr, val):
    save_attr(CONFIG_PATH, attr, val)


def open_energy_editor():
    threading.Thread(daemon=True, target=run_editor, args=(
        "Energy Config", FIELDS, _get, _apply, _save,
    ), kwargs=dict(region_colors=REGION_COLORS)).start()
