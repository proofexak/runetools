"""
Samples EMPTY_SLOT_CHECK pixel every second and prints the actual RGB.
Use this to see what color slot 2 shows when filled vs empty.
Ctrl+C to stop.

    .venv/bin/python -m tanner.checks.slot_check
"""
import time
import mss
import numpy as np

from tanner.config import EMPTY_SLOT_CHECK, BANK_SLOT_2


def main():
    x, y = BANK_SLOT_2
    _, _, expected = EMPTY_SLOT_CHECK
    print(f"Sampling BANK_SLOT_2 ({x}, {y})  |  expected empty color: RGB{expected}\n")

    with mss.mss() as sct:
        try:
            while True:
                shot = sct.grab({"left": x, "top": y, "width": 1, "height": 1})
                px = np.array(shot)[0, 0]
                r, g, b = int(px[2]), int(px[1]), int(px[0])
                er, eg, eb = expected
                diff = max(abs(r - er), abs(g - eg), abs(b - eb))
                print(f"RGB({r:3d},{g:3d},{b:3d})  diff={diff:3d}  {'<< EMPTY' if diff <= 5 else ''}")
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
