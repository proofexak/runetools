"""
Account list + the active account sessions are tagged with.

data/accounts.json (gitignored) holds only non-secret fields — display name and
notes.

    {"active": "Zezima", "accounts": [{"name": "Zezima", "notes": "main"}]}

active() is called at every session start and must never raise into a bot.
RUNETOOLS_ACCOUNT overrides the file (e.g. one container per account).
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_VAR = "RUNETOOLS_ACCOUNT"


def path(root=None):
    return os.path.join(root or ROOT, "data", "accounts.json")


def load(root=None):
    """The account file as a dict; an empty one if missing or unreadable."""
    try:
        with open(path(root), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"active": None, "accounts": []}
    if not isinstance(data, dict):
        return {"active": None, "accounts": []}
    data.setdefault("active", None)
    data.setdefault("accounts", [])
    return data


def save(data, root=None):
    """Write atomically, so a session start never reads half a file."""
    p = path(root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, p)


def active(root=None):
    """Account to tag the starting session with, or None."""
    try:
        return os.environ.get(ENV_VAR) or load(root).get("active") or None
    except Exception:
        return None
