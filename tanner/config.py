"""
Tanner2 bot configuration.
Edit this file to recalibrate positions or change behaviour.
"""

HIDE_TYPE = "green dragonhide"   # green / blue / red / black

# ── RuneLite tile marker colours ──────────────────────────────────────────────

BLUE        = (0,   0, 255)
BLUE_TOL    = 10
MAGENTA     = (255, 0, 255)
MAGENTA_TOL = 10

# ── Scan regions (left, top, width, height) ───────────────────────────────────

ELLIS_REGION = (709, 294, 465, 521)
BANK_REGION  = (75, 184, 501, 348)

# ── Movement detection ────────────────────────────────────────────────────────

MOVEMENT_REGION = (257, 242, 1398, 543)
MOVEMENT_THRESH = 3.0
MOVEMENT_STABLE = 3
MOVEMENT_POLL   = 0.15
WALK_TIMEOUT    = 20.0

# ── Tanning interface ─────────────────────────────────────────────────────────

INTERFACE_BUTTONS = {
    "green dragonhide":  (671, 511, (3, 50, 3)),
    "blue dragonhide":   (785, 510, (3, 5, 64)),
    "red dragonhide":    (896, 510, (50, 5, 3)),
    "black dragonhide":  (1008, 512, (22, 20, 20)),
}
INTERFACE_TOL = 15

TANNING_CHECK = (1045, 317, (72, 62, 51))

# ── Compass / right-click menu ────────────────────────────────────────────────

MENU_ROW_H    = 15
MENU_HEADER   = 15
COMPASS       = (1729, 45)
CHARACTER     = (944, 525)
TANNER_AREA   = [(1618, 558), (1767, 834), (1888, 824), (1888, 778), (1757, 570)]
LOOK_WEST_ROW = 3
AMULET_SLOT   = (1786, 796)
AMULET_MENU_ROW = 4          # 5th right-click option (0-indexed) → Al Kharid teleport

DOUBLE_DOORS_REGION = [(1052, 496), (1062, 466), (1071, 526), (1056, 549)]
TP_BANK_REGION      = (882, 24, 291, 138)

# ── Retry limits ──────────────────────────────────────────────────────────────

MAX_ELLIS_TRIES  = 6
MAX_ELLIS_ROUNDS = 5
ELLIS_ROUND_WAIT = 10

MAX_BANK_RETRIES = 5
MAX_BOOTH_TRIES  = 6

# ── Bank interface ────────────────────────────────────────────────────────────

BANK_CHECK      = (721, 65, (72, 62, 51))
INVENTORY_CHECK = (1697, 741, (62, 53, 41))
DEPOSIT_BTN  = (1020, 825)
BANK_SLOT_1  = (665, 141)
BANK_SLOT_2  = (714, 141)
