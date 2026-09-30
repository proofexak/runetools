"""
Bot discovery and menu building.

Every bot package has a bot.py defining `BOT = Bot(...)`. The overlay menu is
built from whatever discover() finds, so adding a bot never touches root
run.py. bot.py must stay import-light (no pyautogui/mss, no gitignored
config.py at module level) — import those inside the start/configure callables.
"""
import importlib, os, traceback

import lib.events as events
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

TOOL_COLORS = ("#1a1a33", "#2a2a55")
EXIT_COLORS = ("#550000", "#881111")


@dataclass
class Launch:
    label:   str
    start:   Callable                              # start(stats), or start(stats, n) with ask_int
    colors:  Tuple[str, str] = ("#1a3a1a", "#2d6a2d")
    alt:     Optional[Tuple[str, Callable]] = None  # small side button, e.g. ("GE", start_from_ge)
    ask_int: Optional[str] = None                   # prompt for an integer before starting
    configure: Optional[Callable[[], None]] = None  # this launch's editor, as a "⚙" side button


@dataclass
class Bot:
    name:       str
    launches:   List[Launch]
    order:      int = 100
    colors:     Tuple[str, str] = TOOL_COLORS
    configure:  Optional[Callable[[], None]] = None
    stats_line: Optional[Callable[[dict], str]] = None   # extra overlay line during a session
    suite:      str = "osrs"   # which launcher lists it: "osrs" (run.py) or "poe" (crafting_run.py)


def discover(root, suite="osrs"):
    """
    BOT from every package <root>/<pkg>/ (has __init__.py) with a bot.py, sorted
    by (order, name), keeping only bots of the given suite. root must be on sys.path. Non-package dirs are ignored, so
    a standalone script that happens to be called bot.py (woodcutter/) is never
    imported.
    """
    bots = []
    for name in sorted(os.listdir(root)):
        pkg = os.path.join(root, name)
        if not (os.path.isfile(os.path.join(pkg, "__init__.py"))
                and os.path.isfile(os.path.join(pkg, "bot.py"))):
            continue
        try:
            bot = importlib.import_module(f"{name}.bot").BOT
            if not isinstance(bot, Bot):
                raise TypeError(f"BOT is {type(bot).__name__}, not lib.bots.Bot")
            if bot.suite == suite:
                bots.append(bot)
        except Exception as e:   # one broken bot must not take the menu down
            print(f"[BOTS] Skipping {name}: {e!r}")
            events.launcher_error(name, e, "discover")
    return sorted(bots, key=lambda b: (b.order, b.name))


def run_guarded(start, stats, bot=None):
    """Run one session from the menu loop; a crash prints its traceback and
    returns False instead of killing the launcher (e.g. an uncalibrated bot).
    A crash the session didn't already record (e.g. start() failing before the
    session began) goes to log/launcher.jsonl."""
    try:
        start(stats)
        return True
    except Exception as e:
        if not events.was_logged(e):
            events.launcher_error(bot, e, "start")
        traceback.print_exc()
        print("[BOTS] Session crashed — back to the menu.")
        return False


def build_menu(bots, begin, ask_int, tools, flat=False):
    """
    Overlay MENU (lib/overlay.py tuple format) for the given bots.
    begin(bot, start)   — hand a session to the main loop; start(stats) runs it
    ask_int(prompt, cb) — show an integer prompt, call cb(n) on submit
    tools               — [(label, callable)] shown after the bots
    flat                — launches at top level instead of one submenu per bot
    """
    menu = []
    for bot in bots:
        items = []
        for launch in bot.launches:
            item = (launch.label, _command(bot, launch, launch.start, begin, ask_int)) + launch.colors
            if launch.alt and launch.configure:
                raise ValueError(f"{bot.name}/{launch.label}: a launch has one side button — alt or configure")
            if launch.alt:
                alt_label, alt_start = launch.alt
                item += ((alt_label, _command(bot, launch, alt_start, begin, ask_int)),)
            elif launch.configure:
                item += (("⚙", launch.configure),)
            items.append(item)
        if bot.configure:
            items.append(("⚙ Configure", bot.configure) + TOOL_COLORS)
        if flat:
            menu.extend(items)
        else:
            menu.append((bot.name, items) + bot.colors)
    for label, fn in tools:
        menu.append((label, fn) + TOOL_COLORS)
    menu.append(("Exit", lambda: os._exit(0)) + EXIT_COLORS)
    return menu


def _command(bot, launch, start, begin, ask_int):
    if launch.ask_int:
        return lambda: ask_int(launch.ask_int,
                               lambda n: begin(bot, lambda stats: start(stats, n)))
    return lambda: begin(bot, start)
