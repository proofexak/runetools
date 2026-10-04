"""
"⚙ Client Templates" — capture the screen elements unattended mode uses to log
in (lib/client.py): drag a rectangle over each one (via VNC in the container)
and its crop is saved as lib/client_templates/<name>.png. Per-user data,
gitignored, like the digit templates. Capture with nothing on top of the
element (close other editor overlays first).
"""
import json, os, threading

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "lib", "client_templates")

FIELDS = [
    ("Login", "Terms 'Accept' (first run)",  "terms_accept", "region"),
    ("Login", "'Play Now' button",           "login_play",   "region"),
    ("Login", "'Click here to play'",        "welcome_play", "region"),
    ("Game",  "In-game marker (e.g. compass)", "in_game",    "region"),
]


def _regions_path(directory):
    return os.path.join(directory, "regions.json")


def _load_regions(directory=TEMPLATE_DIR):
    try:
        with open(_regions_path(directory), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_template(name, region, directory=TEMPLATE_DIR):
    """Grab `region` (left, top, width, height) and save it as <directory>/<name>.png."""
    from PIL import Image
    from lib.screen import grab
    os.makedirs(directory, exist_ok=True)
    frame, _ = grab(tuple(region))
    Image.fromarray(frame[:, :, ::-1].copy()).save(os.path.join(directory, f"{name}.png"))
    regions = _load_regions(directory)
    regions[name] = list(region)
    with open(_regions_path(directory), "w", encoding="utf-8") as f:
        json.dump(regions, f, indent=1)


def open_editor():
    from lib.config_editor import run_editor
    regions = _load_regions()

    def _get(attr):
        r = regions.get(attr)
        return tuple(r) if r else None

    def _apply(attr, val):
        regions[attr] = list(val)

    threading.Thread(daemon=True, target=run_editor, args=(
        "Client Templates", FIELDS, _get, _apply, save_template,
    )).start()
