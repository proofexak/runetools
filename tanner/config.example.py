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

DOUBLE_DOORS_REGION = [(0, 0), (0, 0), (0, 0), (0, 0)]
TP_BANK_REGION      = (0, 0, 0, 0)

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
BANK_SLOT_1  = (0, 0)
BANK_SLOT_2  = (0, 0)

# ── Behaviour ─────────────────────────────────────────────────────────────────

RESTOCK_GE = True   # if False, bot stops when hides run out instead of restocking
