"""
Tanner descriptor for the overlay menu (see lib/bots.py). Import-light:
config and actions load only when a session starts.
"""
from lib.bots import Bot, Launch

HIDES = [
    # (menu label,       HIDE_TYPE,          bg,        hover)
    ("Green Dragonhide", "green dragonhide", "#1a4a1a", "#2d7a2d"),
    ("Blue Dragonhide",  "blue dragonhide",  "#0d2444", "#1a4a88"),
    ("Red Dragonhide",   "red dragonhide",   "#440d0d", "#882020"),
    ("Black Dragonhide", "black dragonhide", "#1a1a1a", "#333333"),
]


def _start(hide, from_ge=False):
    def start(stats):
        import tanner.config as config
        from tanner.run import run
        config.HIDE_TYPE = hide
        run(stats, start_from_ge=from_ge)
    return start


def _configure():
    from tanner.config_editor import open_editor
    open_editor()


BOT = Bot(
    name       = "Tanning",
    order      = 10,
    colors     = ("#1a3a1a", "#2d6a2d"),
    launches   = [Launch(label, _start(hide), (bg, hover), alt=("GE", _start(hide, from_ge=True)))
                  for label, hide, bg, hover in HIDES],
    configure  = _configure,
    stats_line = lambda s: f"Hides:   {s['run'] * 27}",
)
