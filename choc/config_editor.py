"""
Chocolate dust bot config editor — defines fields and wires up the generic lib editor.
"""
import threading, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import choc.config as cfg
from lib.config_editor import run_editor, save_attr
from lib.restock import setting

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
    ("GE", "Buy Price (fallback)", "GE_BUY_PRICE", "number"),
    ("GE", "Max Price (0 = none)", "GE_MAX_PRICE", "number"),
    ("GE", "Live Prices", "GE_LIVE_PRICES", "bool"),
    ("GE", "Live Margin %", "GE_MARGIN_PCT", "number"),
    ("GE", "Offer Timeout (s)", "GE_OFFER_TIMEOUT", "number"),
    ("GE", "Re-price Every (min)", "GE_REPRICE_MINUTES", "number"),
    ("GE", "Re-price Rounds", "GE_REPRICE_ROUNDS", "number"),
]

REGION_COLORS = {
    "BANK_BOOTH_REGION": "#0000ff",
}


# ── Value helpers ─────────────────────────────────────────────────────────────

def _get(attr):
    if attr.startswith("GE_"):
        return setting(cfg, attr)
    return getattr(cfg, attr, None)


def _apply(attr, val):
    setattr(cfg, attr, val)


def _save(attr, val):
    save_attr(CONFIG_PATH, attr, val)


def open_editor():
    threading.Thread(daemon=True, target=run_editor, args=(
        "Chocolate Config", FIELDS, _get, _apply, _save,
    ), kwargs=dict(region_colors=REGION_COLORS)).start()
