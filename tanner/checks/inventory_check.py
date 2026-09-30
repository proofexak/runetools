"""
Samples INVENTORY_CHECK pixel every second and prints the actual RGB.
Run with inventory open and closed to confirm the check works.
Ctrl+C to stop.

    .venv/bin/python -m tanner.checks.inventory_check
"""
import time
import mss
import numpy as np

from tanner.config import INVENTORY_CHECK, INTERFACE_TOL


def main():
    x, y, expected = INVENTORY_CHECK
    print(f"Sampling ({x}, {y})  |  expected: RGB{expected}  tol={INTERFACE_TOL}\n")

    with mss.mss() as sct:
        try:
            while True:
                shot = sct.grab({"left": x, "top": y, "width": 1, "height": 1})
                px = np.array(shot)[0, 0]
                r, g, b = int(px[2]), int(px[1]), int(px[0])
                er, eg, eb = expected
                diff = max(abs(r - er), abs(g - eg), abs(b - eb))
                match = diff <= INTERFACE_TOL
                print(f"RGB({r:3d},{g:3d},{b:3d})  diff={diff:3d}  {'<< MATCH (open)' if match else ''}")
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
