"""
Crafting bot configuration — copy to config.py and calibrate before use.
"""

# ── Points ─────────────────────────────────────────────────────────────────────

ALT_ORB            = (0, 0)       # currency right-clicked with shift held
CURRENCY_STASH_TAB = (0, 0)       # stash tab holding the alt orb currency
CRAFTING_STASH_TAB = (0, 0)       # stash tab holding the items to craft

# ── Items ──────────────────────────────────────────────────────────────────────
# Each item is one crafting target: its own click point + its own done-check
# point. DONE_CHECK_COLOR below is shared by every item. Use the "+ Add Item"
# button in the config editor to append new entries.

ITEMS = []

# ── Done check ───────────────────────────────────────────────────────────────

DONE_CHECK_COLOR = (0, 0, 0)   # shared across every item
DONE_TOL         = 15
