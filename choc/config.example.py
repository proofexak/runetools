"""
Chocolate dust grinding bot configuration — copy to config.py and calibrate before use.
GE trading fields (search, buy/sell buttons, offer pixels, etc.) live in
lib/ge_config.py instead — this bot reuses that shared config for the actual
GE interaction, only overriding GE_BUY_PRICE via the "GE:" prefix in
choc/config_editor.py. Restock quantity is the session's starting bar count,
passed straight to restock_ge(), not a config value.
"""

# ── RuneLite tile marker colour ─────────────────────────────────────────────
# Bank near the grind spot is an NPC banker (blue), not a booth.
BLUE     = (0, 0, 255)
BLUE_TOL = 10

# ── Bank ─────────────────────────────────────────────────────────────────────
# Region (left, top, width, height) near the character to search for the
# blue banker outline.
BANK_BOOTH_REGION = (0, 0, 0, 0)

# Pixel + expected colour that's only present while the bank interface is open.
BANK_CHECK = (0, 0, (0, 0, 0))

# How many times to retry finding the booth + confirming the bank opened,
# and how long (seconds) to wait for BANK_CHECK to match on each attempt.
BANK_OPEN_RETRIES = 5
BANK_OPEN_TIMEOUT = 5.0

CHOCOLATE_TAB  = (0, 0)   # bank tab holding both chocolate bars and dust
CHOC_BANK_SLOT = (0, 0)   # chocolate bar's slot — assumes the bank is
                          # already on the chocolate tab, no tab clicking
DUST_BANK_SLOT = (0, 0)   # accumulated chocolate dust slot — withdrawn for GE restock
DEPOSIT_BTN    = (0, 0)

# ── Inventory ──────────────────────────────────────────────────────────────
# Pixel + expected colour that's only present while the inventory tab is open.
INVENTORY_CHECK = (0, 0, (0, 0, 0))

# Fixed screen positions — assumes the knife always sits in the last
# inventory slot, and chocolate always lands in the second-to-last slot
# after withdrawing.
KNIFE_SLOT    = (0, 0)
CHOC_INV_SLOT = (0, 0)

# Chocolate bars per inventory load (27 bars + 1 knife = 28 slots).
GRIND_COUNT = 27

# ── GE restock behaviour ─────────────────────────────────────────────────────
# How many times to poll for a GE offer to fill (~3-5s apart) before giving
# up. Offers can take a while, especially buys at market price.
OFFER_WAIT_TRIES = 90
