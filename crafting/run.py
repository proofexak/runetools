"""
Crafting bot session loop.
Control flow is the state machine in crafting/states.py; this module wires
the real actions in as handlers.
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import crafting.config as config
from lib.session import run_session
from crafting.actions import grab_currency, craft_item, release
from crafting.states import build_machine, FINAL_STATES, CYCLE_START

os.makedirs(os.path.join(os.path.dirname(__file__), "log"), exist_ok=True)


def _handlers(session):
    def grab():
        session.stats["step"] = "grabbing currency"
        grab_currency()
        return "ok"

    def craft():
        item = session.next_item()
        n = session.index + 1
        print(f"\n{'='*40}\n  ITEM {n}/{session.total}\n{'='*40}")
        craft_item(item)          # retries until the item's done-check matches
        session.item_done()
        print(f"  Item {n} done — moving to next.")
        return "ok"

    return {"grab_currency": grab, "craft": craft}


def run(stats):
    run_session(
        stats,
        bot          = "crafting",
        params       = {"items": sum(1 for item in config.ITEMS if not item.get("skip"))},
        log_prefix   = os.path.join(os.path.dirname(__file__), "log", "crafting"),
        intro        = [],
        setup        = lambda: None,
        session      = lambda: build_machine(stats, config.ITEMS),
        handlers     = _handlers,
        final_states = FINAL_STATES,
        cycle_start  = CYCLE_START,
        summary      = lambda session, final, last: f"Items: {session.index}/{session.total}",
        game         = "the game",
        teardown     = release,   # shift is held for the whole session
    )
