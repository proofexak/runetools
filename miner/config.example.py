"""
Miner bot configuration — copy to config.py and calibrate before use.
"""

LOCATION = "varrock exp"

# ── RuneLite tile marker colours ──────────────────────────────────────────────

MAGENTA     = (255,   0, 255)
MAGENTA_TOL = 10
BLUE        = (  0,   0, 255)
BLUE_TOL    = 10

# ── Scan regions / slots ──────────────────────────────────────────────────────

ROCK_REGION   = (0, 0, 0, 0)        # area containing both rocks
ORE_SLOT   = (0, 0)             # inventory slot position to monitor and click
SLOT_BG_COLOR = (0, 0, (0, 0, 0)) # click empty slot background to calibrate — only color is used

# ── Compass / right-click menu ────────────────────────────────────────────────

COMPASS        = (0, 0)
MENU_ROW_H     = 15
MENU_HEADER    = 15
LOOK_SOUTH_ROW = 2                  # 3rd option, 0-indexed
