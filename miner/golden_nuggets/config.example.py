"""
Golden Nuggets miner configuration — copy to config.py and calibrate before use.
"""

# ── RuneLite tile marker colours ──────────────────────────────────────────────

MAGENTA     = (255, 0, 255)
MAGENTA_TOL = 10
RED         = (255, 0, 0)
RED_TOL     = 10
GREEN       = (0, 255, 0)
GREEN_TOL   = 10
BLUE        = (0, 0, 255)
BLUE_TOL    = 10

# ── Scan regions ──────────────────────────────────────────────────────────────

PAY_DIRT_REGION  = (0, 0, 0, 0)
HOPPER_REGION    = (0, 0, 0, 0)
STRUT_REGION      = (0, 0, 0, 0)
STRUT_NEAR_REGION = (0, 0, 0, 0)
SACK_REGION      = (0, 0, 0, 0)
SACK_BANK_REGION = (0, 0, 0, 0)
BANK_REGION      = (0, 0, 0, 0)

# ── Character position (for nearest-vein targeting) ───────────────────────────

CHARACTER = (0, 0)

# ── Inventory calibration ─────────────────────────────────────────────────────

INV_ANCHORS   = [(0, 0), (0, 0), (0, 0)]  # [slot1, slot4, slot5] — calibrate via config editor
SLOT_BG_COLOR = (0, 0, (0, 0, 0))         # click center of empty slot — only RGB is used
SLOT_BG_TOL   = 20                         # max avg-color deviation before slot counts as filled

# ── Character / movement ──────────────────────────────────────────────────────

MOVEMENT_REGION = (0, 0, 0, 0)

# ── Bank interface ────────────────────────────────────────────────────────────

BANK_CHECK      = (0, 0, (0, 0, 0))
DEPOSIT_ALL_BTN = (0, 0)

# ── Compass / right-click menu ────────────────────────────────────────────────

COMPASS        = (0, 0)
MENU_ROW_H     = 15
MENU_HEADER    = 15
LOOK_NORTH_ROW = 0
LOOK_EAST_ROW  = 1
LOOK_SOUTH_ROW = 2
LOOK_WEST_ROW  = 3
