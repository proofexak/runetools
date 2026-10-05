"""
The account a starting session is tagged with (`account` in session_start).

data/active_account (gitignored) is one line, the account name. The web app (webapp/)
writes it whenever the active account changes there; bots only read it.
RUNETOOLS_ACCOUNT overrides the file (e.g. one container per account).

active() is called at every session start and must never raise into a bot.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_VAR = "RUNETOOLS_ACCOUNT"


def active_path(root=None):
    return os.path.join(root or ROOT, "data", "active_account")


def active(root=None):
    """Account to tag the starting session with, or None."""
    try:
        if os.environ.get(ENV_VAR):
            return os.environ[ENV_VAR]
        with open(active_path(root), encoding="utf-8") as f:
            return f.readline().strip() or None
    except Exception:
        return None
