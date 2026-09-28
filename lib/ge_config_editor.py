"""
GE config editor — defines fields and wires up the generic lib editor.
"""
import threading, os, sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import lib.ge_config as cfg
from lib.config_editor import run_editor, save_attr

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "ge_config.py")

FIELDS = [
    ("Teleport",   "Ring Slot",            "RING_SLOT",            "point"),
    ("Teleport",   "Ring Menu Region",     "RING_MENU_REGION",     "region"),
    ("Navigation", "Compass",              "COMPASS",              "point"),
    ("Navigation", "Movement Region",      "MOVEMENT_REGION",      "region"),
    ("Banker",     "Approach Region",      "GE_APPROACH_REGION",   "region"),
    ("Banker",     "GE Region",            "GE_REGION",            "region"),
    ("Banker",     "Bank Check",           "BANK_CHECK",           "point_color"),
    ("Bank",       "Second Tab",           "SECOND_TAB",           "point"),
    ("Bank",       "Notes Check",          "NOTES_CHECK",          "point_color"),
    ("Bank",       "Notes Button",         "NOTES_BTN",            "point"),
    ("Bank",       "Bank Slot 1",          "BANK_SLOT_1",          "point"),
    ("Bank",       "Deposit Button",       "DEPOSIT_BTN",          "point"),
    ("Bank",       "Bank Area",            "GE_BANK_AREA",         "region"),
    ("GE",         "GE Check",             "GE_CHECK",             "point_color"),
    ("GE",         "Sell Slot",            "SELL_SLOT",            "point"),
    ("GE",         "Price Button",         "PRICE_BTN",            "point"),
    ("GE",         "Confirm Button",       "CONFIRM_BTN",          "point"),
    ("GE",         "Yes Button",           "SELL_YES_BTN",         "point"),
    ("GE",         "Offer Complete",       "OFFER_COMPLETE",       "point_color"),
    ("GE",         "Retrieve Slot 1",      "RETRIEVE_SLOT_1",      "point"),
    ("GE",         "Buy Button",           "BUY_BTN",              "point"),
    ("GE",         "Search Result",        "BUY_SEARCH_RESULT",    "point"),
    ("GE",         "Quantity Button",      "BUY_QUANTITY_BTN",     "point"),
    ("GE",         "Retrieve Slot 2",      "RETRIEVE_SLOT_2",      "point"),
]

REGION_COLORS = {
    "RING_MENU_REGION":   "#ff88ff",
    "GE_APPROACH_REGION": "#ff8800",
    "GE_REGION":        "#0088ff",
    "GE_BANK_AREA":     "#44ff88",
    "MOVEMENT_REGION":  "#ffff00",
}


def _get(attr):
    return getattr(cfg, attr, None)


def _apply(attr, val):
    setattr(cfg, attr, val)


def _save(attr, val):
    save_attr(CONFIG_PATH, attr, val)


def open_ge_editor():
    threading.Thread(daemon=True, target=run_editor, args=(
        "GE Config", FIELDS, _get, _apply, _save,
    ), kwargs=dict(region_colors=REGION_COLORS)).start()
