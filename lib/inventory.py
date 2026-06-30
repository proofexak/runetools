"""
Inventory slot position calculator.

Calibrate three anchor points (stored as a single INV_ANCHORS list):
  anchors[0] — center of slot 1  (row 1, col 1)
  anchors[1] — center of slot 4  (row 1, col 4)
  anchors[2] — center of slot 5  (row 2, col 1)

Column spacing and row spacing are derived and all 28 slot centers computed.
"""


def get_slots(anchors):
    """
    Return list of 28 (x, y) slot centers, left-to-right top-to-bottom.
    anchors = [(x1,y1), (x4,y1), (x1,y2)]
    """
    (x1, y1), (x4, _), (_, y2) = anchors
    col_step = (x4 - x1) / 3.0
    row_step = float(y2 - y1)
    return [
        (round(x1 + col * col_step), round(y1 + row * row_step))
        for row in range(7)
        for col in range(4)
    ]
