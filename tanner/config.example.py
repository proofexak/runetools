"""
Tanner bot configuration — copy to config.py and calibrate before use.
"""

HIDE_TYPE = "green dragonhide"   # green / blue / red / black

# ── RuneLite tile marker colours ──────────────────────────────────────────────

BLUE        = (0,   0, 255)
BLUE_TOL    = 10
MAGENTA     = (255, 0, 255)
MAGENTA_TOL = 10

# ── Scan regions (left, top, width, height) ───────────────────────────────────

ELLIS_REGION = (0, 0, 0, 0)
BANK_REGION  = (0, 0, 0, 0)

# ── Movement detection ────────────────────────────────────────────────────────

MOVEMENT_REGION = (0, 0, 0, 0)
MOVEMENT_THRESH = 3.0
MOVEMENT_STABLE = 3
MOVEMENT_POLL   = 0.15
WALK_TIMEOUT    = 20.0

# ── Tanning interface ─────────────────────────────────────────────────────────

INTERFACE_BUTTONS = {
    "green dragonhide":  (0, 0, (0, 0, 0)),
    "blue dragonhide":   (0, 0, (0, 0, 0)),
    "red dragonhide":    (0, 0, (0, 0, 0)),
    "black dragonhide":  (0, 0, (0, 0, 0)),
}
INTERFACE_TOL = 15

TANNING_CHECK = (0, 0, (0, 0, 0))

# ── Compass / right-click menu ────────────────────────────────────────────────

MENU_ROW_H    = 15
MENU_HEADER   = 15
COMPASS       = (0, 0)
CHARACTER     = (0, 0)
TANNER_AREA   = [(0, 0), (0, 0), (0, 0), (0, 0), (0, 0)]
LOOK_WEST_ROW = 3
AMULET_SLOT   = (0, 0)
AMULET_MENU_ROW = 4          # 5th right-click option (0-indexed) → Al Kharid teleport
# True: a left-click on the worn glory teleports to Al Kharid — set that in RuneLite's
# Menu Entry Swapper first (unswapped, a left-click REMOVES the amulet). False: right-click
# menu, AMULET_MENU_ROW. A config without this line keeps the right-click menu.
AMULET_LEFT_CLICK_TP = True

DOUBLE_DOORS_REGION = [(0, 0), (0, 0), (0, 0), (0, 0)]
TP_BANK_REGION      = (0, 0, 0, 0)   # clicked after the doors: walk into the bank
TP_BOOTH_REGION     = (0, 0, 0, 0)   # magenta booth searched here once the walk stopped

# ── Retry limits ──────────────────────────────────────────────────────────────

MAX_ELLIS_TRIES  = 6
MAX_ELLIS_ROUNDS = 5
ELLIS_ROUND_WAIT = 10

MAX_BANK_RETRIES = 5
MAX_BOOTH_TRIES  = 6

# ── Bank interface ────────────────────────────────────────────────────────────

BANK_CHECK      = (0, 0, (0, 0, 0))
INVENTORY_CHECK = (0, 0, (0, 0, 0))
DEPOSIT_BTN  = (0, 0)
HIDE_TAB     = (0, 0)
BANK_SLOT_1  = (0, 0)
BANK_SLOT_2  = (0, 0)

# Dedicated pixel + colour for "is bank slot 2 empty" — calibrated directly
# at that slot rather than reusing BANK_CHECK's background colour.
EMPTY_SLOT_CHECK = (0, 0, (0, 0, 0))

# ── Behaviour ─────────────────────────────────────────────────────────────────

RESTOCK_GE = True   # if False, bot stops when hides run out instead of restocking

# ── GE restock (lib/restock.py) ───────────────────────────────────────────────
# A line missing here falls back to lib/ge_config.py, where older configs kept it.

GE_QUANTITY        = 1       # hides bought per restock
GE_BUY_PRICE       = 2000    # per hide, when live prices are off or the API can't be reached
GE_MAX_PRICE       = 0       # never offer more per hide (0 = no cap) — one value for every hide type
GE_OFFER_TIMEOUT   = 60      # seconds to wait for an offer when re-pricing is off
GE_REPRICE_MINUTES = 5       # offer not complete after this long: collect, edit its price (0 = off)
GE_REPRICE_ROUNDS  = 6       # price edits before the restock gives up
