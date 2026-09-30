"""
Chocolate grind decisions — pure, no screen or config access.
"""


def restock_due(remaining, grind_count):
    """True if, after grinding one more batch, fewer than a batch of bars would
    be left — so this batch's bank visit is followed by a GE restock."""
    return (remaining - grind_count) < grind_count
