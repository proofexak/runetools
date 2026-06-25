"""
Grand Exchange configuration — shared across all bots that use lib/ge.py.
Calibrate all points before first use.
"""

# ── Colors (RuneLite highlights) ──────────────────────────────────────────────

BLUE        = (0,   0, 255)
BLUE_TOL    = 10
MAGENTA     = (255, 0, 255)
MAGENTA_TOL = 10

# ── Teleport ──────────────────────────────────────────────────────────────────

RING_SLOT        = (1843, 916)
RING_MENU_ROW    = 2        # 3rd right-click option (0-indexed) → GE teleport
RING_MENU_REGION = (1687, 749, 200, 292)

# ── Navigation ────────────────────────────────────────────────────────────────

COMPASS       = (1730, 45)
LOOK_WEST_ROW = 3
MENU_ROW_H    = 15
MENU_HEADER   = 15

# ── Movement detection ────────────────────────────────────────────────────────

MOVEMENT_REGION = (257, 242, 1398, 543)
MOVEMENT_THRESH = 3.0
MOVEMENT_STABLE = 3
MOVEMENT_POLL   = 0.15
WALK_TIMEOUT    = 20.0

# ── Banker (blue hull) ────────────────────────────────────────────────────────

GE_APPROACH_REGION = (1178, 419, 273, 310)
GE_REGION        = (919, 425, 221, 213)
BANK_CHECK       = (837, 813, (138, 33, 30))

# ── Bank interface ────────────────────────────────────────────────────────────

SECOND_TAB   = (695, 102)       # second bank tab — also drag target for hides
NOTES_CHECK  = (655, 836, (124, 29, 27))
NOTES_BTN    = (654, 824)
BANK_SLOT_1  = (664, 143)
DEPOSIT_BTN  = (1019, 823)
GE_BANK_AREA = (598, 123, 477, 681)

# ── GE agent (magenta) ────────────────────────────────────────────────────────

GE_CHECK        = (711, 315, (70, 61, 50))

# ── GE interface (sell + buy share most buttons) ──────────────────────────────

SELL_SLOT            = (1767, 758)
PRICE_BTN            = (963, 489)
CONFIRM_BTN          = (837, 565)
SELL_YES_BTN         = (904, 496)
OFFER_COMPLETE = (661, 444, (0, 95, 0))
RETRIEVE_SLOT_1      = (987, 563)
BUY_BTN              = (635, 428)
BUY_SEARCH_RESULT    = (95, 918)
BUY_QUANTITY_BTN     = (792, 490)
RETRIEVE_SLOT_2      = (1042, 565)

# ── Settings ──────────────────────────────────────────────────────────────────

GE_QUANTITY  = 1
GE_BUY_PRICE = 2000

# ── Retry limits ──────────────────────────────────────────────────────────────

MAX_BANKER_TRIES = 20
MAX_AGENT_TRIES  = 20
MAX_OFFER_TRIES  = 4
GE_MAX_RETRIES   = 4
