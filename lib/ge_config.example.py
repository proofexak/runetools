"""
Grand Exchange configuration — copy to ge_config.py and calibrate before use.
"""

# ── Colors (RuneLite highlights) ──────────────────────────────────────────────

BLUE        = (0,   0, 255)
BLUE_TOL    = 10
MAGENTA     = (255, 0, 255)
MAGENTA_TOL = 10

# ── Teleport ──────────────────────────────────────────────────────────────────

RING_SLOT        = (0, 0)
RING_MENU_ROW    = 2        # 3rd right-click option (0-indexed) → GE teleport
RING_MENU_REGION = (0, 0, 0, 0)
# True: a left-click on the worn ring of wealth teleports to the GE — set that in RuneLite's
# Menu Entry Swapper first (unswapped, a left-click REMOVES the ring). False: right-click
# menu, RING_MENU_ROW / RING_MENU_REGION. A config without this line keeps the right-click menu.
RING_LEFT_CLICK_TP = True

# ── Navigation ────────────────────────────────────────────────────────────────

COMPASS       = (0, 0)
LOOK_WEST_ROW = 3
MENU_ROW_H    = 15
MENU_HEADER   = 15

# ── Movement detection ────────────────────────────────────────────────────────

MOVEMENT_REGION = (0, 0, 0, 0)
MOVEMENT_THRESH = 3.0
MOVEMENT_STABLE = 3
MOVEMENT_POLL   = 0.15
WALK_TIMEOUT    = 20.0

# ── Banker (blue hull) ────────────────────────────────────────────────────────

GE_APPROACH_REGION = (0, 0, 0, 0)
GE_REGION        = (0, 0, 0, 0)
BANK_CHECK       = (0, 0, (0, 0, 0))

# ── Bank interface ────────────────────────────────────────────────────────────

SECOND_TAB   = (0, 0)
NOTES_CHECK  = (0, 0, (0, 0, 0))
NOTES_BTN    = (0, 0)
BANK_SLOT_1  = (0, 0)
DEPOSIT_BTN  = (0, 0)
GE_BANK_AREA = (0, 0, 0, 0)

# ── GE agent (magenta) ────────────────────────────────────────────────────────

GE_CHECK        = (0, 0, (0, 0, 0))

# ── GE interface (sell + buy share most buttons) ──────────────────────────────

SELL_SLOT            = (0, 0)
PRICE_BTN            = (0, 0)
CONFIRM_BTN          = (0, 0)
SELL_YES_BTN         = (0, 0)
OFFER_COMPLETE       = (0, 0, (0, 0, 0))
RETRIEVE_SLOT_1      = (0, 0)
BUY_BTN              = (0, 0)
BUY_SEARCH_RESULT    = (0, 0)
BUY_QUANTITY_BTN     = (0, 0)
RETRIEVE_SLOT_2      = (0, 0)

# ── Settings ──────────────────────────────────────────────────────────────────

GE_QUANTITY  = 1
GE_BUY_PRICE = 2000

# ── Retry limits ──────────────────────────────────────────────────────────────

MAX_BANKER_TRIES = 20
MAX_AGENT_TRIES  = 20
MAX_OFFER_TRIES  = 4
GE_MAX_RETRIES   = 4
