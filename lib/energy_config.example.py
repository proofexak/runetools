"""
Energy/stamina configuration — copy to energy_config.py and calibrate before use.
"""

# ── Run energy region ──────────────────────────────────────────────────────
# Region (left, top, width, height) tightly around the run-energy percentage
# text under the minimap orb (e.g. "84%").
ENERGY_REGION = (0, 0, 0, 0)

# ── Stamina potions ─────────────────────────────────────────────────────────
# Inventory slot (x, y) of a stamina potion.
STAMINA_POTION_SLOT = (0, 0)

# Drink the whole bottle (4 doses) when energy drops below this percentage.
DRINK_THRESHOLD = 50

# ── Bank (for withdrawing stamina potions kept stocked in the bank) ─────────
# Pixel + expected colour that's only present while the bank interface is
# open — same idea as tanner's BANK_CHECK.
BANK_CHECK = (0, 0, (0, 0, 0))

DEPOSIT_BTN = (0, 0)
POTION_TAB  = (0, 0)
BANK_SLOT_1 = (0, 0)

INVENTORY_CHECK = (0, 0, (0, 0, 0))

# Region (left, top, width, height) near the character to search for the
# magenta bank booth outline when reopening the bank after drinking.
BANK_BOOTH_REGION = (0, 0, 0, 0)
