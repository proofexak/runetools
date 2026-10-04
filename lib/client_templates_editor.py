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
    ("Game",  "In-game marker (fixed: minimap frame / tab icon, NOT the compass)", "in_game", "region"),
]


def _regions_path(directory):
    return os.path.join(directory, "regions.json")


def _load_regions(directory=TEMPLATE_DIR):
    try:
        with open(_regions_path(directory), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_template(name, region, directory=TEMPLATE_DIR, snapshot=None):
    """Save `region` (left, top, width, height) as <directory>/<name>.png — cropped
    from `snapshot` (a BGR frame of the screen) if given, else grabbed live."""
    from PIL import Image
    if len(region) != 4 or not all(isinstance(v, int) for v in region):
        raise ValueError("drag a rectangle (▭) — polygons can't be used as templates")
    l, t, w, h = region
    if snapshot is not None:
        frame = snapshot[t:t + h, l:l + w]
    else:
        from lib.screen import grab
        frame, _ = grab(tuple(region))
    os.makedirs(directory, exist_ok=True)
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

    def _save(attr, val):
        # the capture overlay hides the screen in Xvfb: crop from its snapshot
        save_template(attr, val, snapshot=config_editor.last_snapshot[0])

    import lib.config_editor as config_editor
    threading.Thread(daemon=True, target=run_editor, args=(
        "Client Templates", FIELDS, _get, _apply, _save,
    )).start()
