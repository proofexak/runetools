"""
Chocolate dust grinding bot configuration — copy to config.py and calibrate before use.
GE trading fields (search, buy/sell buttons, offer pixels, etc.) live in
lib/ge_config.py instead — this bot reuses that shared config for the actual
GE interaction; what it buys and at what price is the GE_* section below.
Restock quantity is asked at launch ("Chocolate bars to buy per restock?") and
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

CHOCOLATE_TAB  = (0, 0)   # bank tab holding both chocolate bars and dust — clicked every visit
CHOC_BANK_SLOT = (0, 0)   # chocolate bar's slot on that tab
DUST_BANK_SLOT = (0, 0)   # accumulated chocolate dust slot — withdrawn for GE restock
DEPOSIT_BTN    = (0, 0)

# The corner of the chocolate bar stack (CHOC_BANK_SLOT) where its count is drawn. No count at
# a bank visit = 1 or none left = restock (like tanner's hide count). The dust stack's count box
# is this one moved to DUST_BANK_SLOT (no count there = nothing to sell, the restock only buys).
# Box just the digits, not the icon. The bot won't start without it.
CHOC_COUNT_REGION = (0, 0, 0, 0)

# ── Inventory ──────────────────────────────────────────────────────────────
# A pixel of the backpack tab's red "selected" highlight (bottom side-tab bar) + its colour:
# only there while the inventory is the open panel (the panel frame looks the same for every
# tab — don't pick it). Before each batch the bot clicks this point to open the inventory.
INVENTORY_CHECK = (0, 0, (0, 0, 0))

# Fixed screen positions — assumes the knife always sits in the last
# inventory slot, and chocolate always lands in the second-to-last slot
# after withdrawing.
KNIFE_SLOT    = (0, 0)
CHOC_INV_SLOT = (0, 0)
# An empty inventory slot's colour: after withdrawing, CHOC_INV_SLOT still matching it = fewer
# than 27 bars → they go back and the bot restocks. The bot won't start without it.
EMPTY_SLOT_BG  = (0, 0, (0, 0, 0))   # click the centre of an empty slot — only the RGB is used
EMPTY_SLOT_TOL = 20

# Chocolate bars per inventory load (27 bars + 1 knife = 28 slots).
GRIND_COUNT = 27

# ── GE restock (lib/restock.py) ───────────────────────────────────────────────
RESTOCK_GE         = True    # if False, the bot stops when the bars run out instead of restocking
SELL_INV_SLOT      = (0, 0)  # inventory slot the noted dust lands in — clicked to sell it
GE_BUY_PRICE       = 40      # per bar, when live prices are off or the API can't be reached
GE_MAX_PRICE       = 60      # never offer more per bar (0 = no cap)
GE_OFFER_TIMEOUT   = 360     # seconds to wait for an offer when re-pricing is off
GE_REPRICE_MINUTES = 5       # offer not complete after this long: collect, edit its price (0 = off)
GE_REPRICE_ROUNDS  = 6       # price edits before the restock gives up
GE_REPRICE_STEP    = 5       # fresh price within this many gp of the offer: step it (buy +, sell -)
