"""
The active account sessions are tagged with (+ the prototype dashboard's account list).

data/active_account (gitignored) is one line, the account name. The web app (webapp/)
writes it whenever the active account changes; bots only read it. The prototype
dashboard keeps its list in data/accounts.json and mirrors its active one into
data/active_account too:

    {"active": "Zezima", "accounts": [{"name": "Zezima", "notes": "main"}]}

active() is called at every session start and must never raise into a bot.
RUNETOOLS_ACCOUNT overrides the file (e.g. one container per account).
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_VAR = "RUNETOOLS_ACCOUNT"


def path(root=None):
    return os.path.join(root or ROOT, "data", "accounts.json")


def active_path(root=None):
    return os.path.join(root or ROOT, "data", "active_account")


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


def _replace(p, text):
    """Write atomically, so a session start never reads half a file."""
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, p)


def save(data, root=None):
    _replace(path(root), json.dumps(data, indent=2))
    if data.get("active"):
        _replace(active_path(root), data["active"] + "\n")
    elif os.path.exists(active_path(root)):
        os.remove(active_path(root))


def _read_active_file(root=None):
    try:
        with open(active_path(root), encoding="utf-8") as f:
            return f.readline().strip() or None
    except (OSError, ValueError):
        return None


def active(root=None):
    """Account to tag the starting session with, or None."""
    try:
        return (os.environ.get(ENV_VAR) or _read_active_file(root)
                or load(root).get("active") or None)
    except Exception:
        return None
