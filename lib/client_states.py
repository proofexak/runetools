"""
RuneLite client lifecycle for unattended runs — states and transitions only.
Handlers (launching RuneLite, finding screens by template, clicking) live in
lib/client.py; this module stays pure so it can be tested with stub handlers.

  launch → wait_login → [accept_terms → wait_login] → click_play → wait_welcome
         → click_welcome → wait_in_game → in_game
  any wait that times out → failed; "already in game" short-circuits to in_game
"""
from transitions import Machine

FINAL_STATES = {"in_game", "failed"}

STATES = ["launch", "wait_login", "accept_terms", "click_play", "wait_welcome",
          "click_welcome", "wait_in_game", "in_game", "failed"]

_WAITS = ["wait_login", "wait_welcome", "wait_in_game"]

TRANSITIONS = [
    {"trigger": "ok",      "source": "launch",        "dest": "wait_login"},
    {"trigger": "ok",      "source": "wait_login",    "dest": "click_play"},
    {"trigger": "terms",   "source": "wait_login",    "dest": "accept_terms"},
    {"trigger": "ok",      "source": "accept_terms",  "dest": "wait_login"},
    {"trigger": "ok",      "source": "click_play",    "dest": "wait_welcome"},
    {"trigger": "ok",      "source": "wait_welcome",  "dest": "click_welcome"},
    {"trigger": "ok",      "source": "click_welcome", "dest": "wait_in_game"},
    {"trigger": "ok",      "source": "wait_in_game",  "dest": "in_game"},
    {"trigger": "in_game", "source": ["launch"] + _WAITS, "dest": "in_game"},
    {"trigger": "timeout", "source": _WAITS,          "dest": "failed"},
]


class ClientSession:
    def __init__(self, stats):
        self.stats = stats
        self.target = None      # where the next click goes (set by a wait handler)
        self.deadline = None    # when the current wait gives up
        self.reason = None      # why the login failed


def build_machine(stats):
    session = ClientSession(stats)
    Machine(model=session, states=STATES, transitions=TRANSITIONS,
            initial="launch", auto_transitions=False)
    return session
