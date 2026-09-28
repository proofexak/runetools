"""
Chocolate dust bot config editor — defines fields and wires up the generic lib editor.
"""
import threading, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import choc.config as cfg
import lib.ge_config as ge_cfg
from lib.config_editor import run_editor, save_attr

_GE_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "lib", "ge_config.py")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.py")

FIELDS = [
    ("Bank", "Bank Booth Region", "BANK_BOOTH_REGION", "region"),
    ("Bank", "Bank Check",        "BANK_CHECK",        "point_color"),
    ("Bank", "Chocolate Tab",     "CHOCOLATE_TAB",      "point"),
    ("Bank", "Chocolate Bank Slot", "CHOC_BANK_SLOT",   "point"),
    ("Bank", "Dust Bank Slot",    "DUST_BANK_SLOT",     "point"),
    ("Bank", "Deposit Button",    "DEPOSIT_BTN",        "point"),
    ("Bank", "Bank Open Retries", "BANK_OPEN_RETRIES",  "number"),
    ("Bank", "Bank Open Timeout (s)", "BANK_OPEN_TIMEOUT", "number"),
    ("Inventory", "Inventory Check",    "INVENTORY_CHECK", "point_color"),
    ("Inventory", "Knife Slot",         "KNIFE_SLOT",    "point"),
    ("Inventory", "Chocolate Inv Slot", "CHOC_INV_SLOT", "point"),
    ("Behaviour", "Grind Count", "GRIND_COUNT", "number"),
    ("GE", "Buy Price", "GE:GE_BUY_PRICE", "number"),
    ("GE", "Offer Wait Tries", "OFFER_WAIT_TRIES", "number"),
]

REGION_COLORS = {
    "BANK_BOOTH_REGION": "#0000ff",
}


# ── Value helpers ─────────────────────────────────────────────────────────────

def _get(attr):
    if attr.startswith("GE:"):
        return getattr(ge_cfg, attr[3:], None)
    return getattr(cfg, attr, None)


def _apply(attr, val):
    if attr.startswith("GE:"):
        setattr(ge_cfg, attr[3:], val)
    else:
        setattr(cfg, attr, val)


def _save(attr, val):
    if attr.startswith("GE:"):
        save_attr(_GE_CONFIG_PATH, attr[3:], val)
        return

    save_attr(CONFIG_PATH, attr, val)


def open_editor():
    threading.Thread(daemon=True, target=run_editor, args=(
        "Chocolate Config", FIELDS, _get, _apply, _save,
    ), kwargs=dict(region_colors=REGION_COLORS)).start()
