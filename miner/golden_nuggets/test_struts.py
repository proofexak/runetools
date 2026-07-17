"""
Standalone strut fix test — switch to OSRS before running.
"""
import time, sys, os
import numpy as np
import mss

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from miner.golden_nuggets.miner import orient_east, click_struts, _log
import miner.golden_nuggets.config as config


def scan_region(name, region):
    l, t, w, h = region
    with mss.MSS() as sct:
        mon = sct.monitors[1]
        shot = sct.grab({"left": mon["left"] + l, "top": mon["top"] + t, "width": w, "height": h})
    frame = np.array(shot)[:, :, :3]
    # Sample the 10 most common colors in the region
    pixels = frame.reshape(-1, 3)
    # Check configured color
    mr, mg, mb = config.STRUT_COLOR
    tol = config.STRUT_TOL
    mask = (
        (pixels[:, 2] >= mr - tol) & (pixels[:, 2] <= mr + tol) &
        (pixels[:, 1] >= mg - tol) & (pixels[:, 1] <= mg + tol) &
        (pixels[:, 0] >= mb - tol) & (pixels[:, 0] <= mb + tol)
    )
    _log(f"{name}: {mask.sum()} pixels matching STRUT_COLOR {config.STRUT_COLOR} ±{tol}")
    # Show a few sample pixels from the region corners for reference
    h_f, w_f = frame.shape[:2]
    samples = [
        ("TL", frame[5, 5]),
        ("TR", frame[5, w_f - 5]),
        ("BL", frame[h_f - 5, 5]),
        ("BR", frame[h_f - 5, w_f - 5]),
        ("C",  frame[h_f // 2, w_f // 2]),
    ]
    for label, px in samples:
        b, g, r = int(px[0]), int(px[1]), int(px[2])
        print(f"  {label}: RGB({r},{g},{b})")


_log("Starting strut diagnostic in 3s...")
time.sleep(3)

orient_east()
time.sleep(0.5)

_log("--- Scanning regions ---")
scan_region("STRUT_REGION", config.STRUT_REGION)
scan_region("STRUT_NEAR_REGION", config.STRUT_NEAR_REGION)

_log("--- Running click_struts ---")
click_struts()

_log("Done.")
