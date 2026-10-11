"""
An account's play schedule (PRO-102), as the web app hands it over: it generates the blocks
and writes data/schedules/<account>.json (gitignored) whenever they change; schedule mode in
lib/headless.py (SCHEDULE=1) re-reads it and plays only inside a block.

    {"account": "alt1", "enabled": true, "timezone": "Europe/Warsaw", "written": "...",
     "blocks": [{"id": 12, "start": 1791734400, "end": 1791741000,
                 "bot": "Tanning", "launch": "Green Dragonhide", "value": "Al Kharid"}, ...]}

start / end are epoch seconds (UTC); blocks never overlap. Pure apart from load()'s read,
which never raises: a missing or broken file means no play.
"""
import json, os
from typing import NamedTuple, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Block(NamedTuple):
    id: int
    start: float
    end: float
    bot: str
    launch: str
    value: Optional[str]


def path_for(account, root=None):
    """data/schedules/<account>.json, or None without an account."""
    if not account:
        return None
    return os.path.join(root or ROOT, "data", "schedules", f"{account}.json")


def _block(row):
    try:
        value = row.get("value")
        block = Block(int(row["id"]), float(row["start"]), float(row["end"]), str(row["bot"]),
                      str(row["launch"]), None if value is None else str(value))
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    return block if block.end > block.start else None


def load(path):
    """(enabled, blocks sorted by start); (False, []) when the file is missing or unreadable."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        rows = data["blocks"]
        if not isinstance(rows, list):
            return False, []
        blocks = sorted((b for b in map(_block, rows) if b), key=lambda b: b.start)
        return data.get("enabled") is True, blocks
    except Exception:
        return False, []


def current(blocks, now):
    """The block running at `now` (start <= now < end), or None."""
    return next((b for b in blocks if b.start <= now < b.end), None)


def next_start(blocks, now):
    """When the next block starts after `now`, or None."""
    return min((b.start for b in blocks if b.start > now), default=None)
