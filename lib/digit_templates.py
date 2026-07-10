"""
Template-matching digit reader for small in-game bitmap fonts.

General OCR (Tesseract) is unreliable on OSRS's tiny UI numerals — tested
extensively against the run-energy readout and it misreads/drops digits
even on clean, well-padded, correctly-segmented single-character crops.
Since the in-game font is a fixed, non-anti-aliased bitmap font, exact
pixel-template matching is far more reliable.

Templates are gitignored, per-user calibration data (rendering can differ
slightly with display scaling / RuneLite settings) — build them with
calibrate_energy_digits.py before relying on read_number().
"""
import os
import numpy as np
from PIL import Image, ImageOps

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "digit_templates")
THRESHOLD  = 140   # brightness cutoff separating in-game text from background
SCALE      = 8     # upscale factor applied before segmenting/matching
GLYPH_SIZE = (32, 48)  # canonical (w, h) every glyph is normalised to


def preprocess(rgb_img):
    """Screenshot region (RGB) -> inverted, upscaled, binarized L image
    (black ink on white background)."""
    gray = rgb_img.convert("L").resize(
        (rgb_img.width * SCALE, rgb_img.height * SCALE), Image.NEAREST)
    bw = gray.point(lambda p: 255 if p > THRESHOLD else 0)
    return ImageOps.invert(bw.convert("L"))


def segment_glyphs(bw_img):
    """Binarized (black-on-white) image -> list of tightly-cropped,
    size-normalised single-glyph images, left to right."""
    arr = np.array(bw_img)
    ink = arr < 128

    col_has_ink = ink.any(axis=0)
    ranges = []
    in_run = False
    for x, v in enumerate(col_has_ink):
        if v and not in_run:
            start = x; in_run = True
        elif not v and in_run:
            ranges.append((start, x)); in_run = False
    if in_run:
        ranges.append((start, len(col_has_ink)))

    glyphs = []
    for x0, x1 in ranges:
        col_ink = ink[:, x0:x1]
        rows = np.where(col_ink.any(axis=1))[0]
        if len(rows) == 0:
            continue
        y0, y1 = rows[0], rows[-1] + 1
        crop = bw_img.crop((x0, y0, x1, y1)).resize(GLYPH_SIZE, Image.NEAREST)
        glyphs.append(crop)
    return glyphs


def load_templates():
    templates = {}
    if not os.path.isdir(TEMPLATE_DIR):
        return templates
    for fname in os.listdir(TEMPLATE_DIR):
        if fname.endswith(".png"):
            digit = fname[:-4]
            templates[digit] = np.array(Image.open(os.path.join(TEMPLATE_DIR, fname)))
    return templates


def save_template(digit, glyph_img):
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    glyph_img.save(os.path.join(TEMPLATE_DIR, f"{digit}.png"))


def match_glyph(glyph_img, templates, max_diff_frac=0.15):
    """Best-matching digit for a single glyph, or None if no template is
    close enough (fraction of mismatched pixels above max_diff_frac)."""
    if not templates:
        return None
    arr = np.array(glyph_img) < 128  # boolean ink mask
    best_digit, best_frac = None, 1.0
    for digit, tmpl in templates.items():
        tmpl_ink = tmpl < 128
        diff_frac = np.count_nonzero(arr != tmpl_ink) / arr.size
        if diff_frac < best_frac:
            best_digit, best_frac = digit, diff_frac
    if best_frac > max_diff_frac:
        return None
    return best_digit


def read_number(region, templates=None, pad=6):
    """Grab `region` (left, top, w, h), return (raw_string, int_or_None)."""
    import mss
    if templates is None:
        templates = load_templates()

    l, t, w, h = region
    l -= pad;  t -= pad;  w += pad * 2;  h += pad * 2
    with mss.mss() as sct:
        shot = sct.grab({"left": l, "top": t, "width": w, "height": h})
    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    bw = preprocess(img)
    glyphs = segment_glyphs(bw)

    raw = ""
    for g in glyphs:
        digit = match_glyph(g, templates)
        raw += digit if digit is not None else "?"

    value = int(raw) if raw and raw.isdigit() else None
    return raw, value
