"""
Synthetic screen for tests: stands in for `mss.mss()` so screen-reading code
runs against numpy canvases instead of the real display.

Canvases are (h, w, 3) uint8 in BGR order — the same layout the code gets from
`np.array(mss_shot)[:, :, :3]`.
"""
import numpy as np


def canvas(w, h, rgb=(0, 0, 0)):
    c = np.zeros((h, w, 3), dtype=np.uint8)
    c[:, :] = rgb[::-1]
    return c


def paint(c, x, y, w, h, rgb):
    """Fill a w×h rectangle whose top-left is (x, y) with rgb."""
    c[y:y + h, x:x + w] = rgb[::-1]
    return c


class _Shot:
    def __init__(self, bgr):
        h, w = bgr.shape[:2]
        self._bgra = np.dstack([bgr, np.full((h, w), 255, dtype=np.uint8)])
        self.size = (w, h)
        self.bgra = self._bgra.tobytes()

    def __array__(self, dtype=None):
        return self._bgra if dtype is None else self._bgra.astype(dtype)


class FakeScreen:
    """Controller: what the next grab sees. show() = constant canvas,
    sequence() = one canvas per grab (last one repeats)."""

    def __init__(self, w=400, h=400):
        self.w, self.h = w, h
        self.grabs = 0
        self._frames = [canvas(w, h)]

    def show(self, c):
        self._frames = [c]

    def sequence(self, frames):
        self._frames = list(frames)

    def _next(self):
        self.grabs += 1
        return self._frames.pop(0) if len(self._frames) > 1 else self._frames[0]

    def mss(self):
        screen = self

        class _MSS:
            monitors = [{}, {"left": 0, "top": 0, "width": screen.w, "height": screen.h}]

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def grab(self, box):
                l, t, w, h = box["left"], box["top"], box["width"], box["height"]
                frame = screen._next()
                assert 0 <= l and 0 <= t and l + w <= frame.shape[1] and t + h <= frame.shape[0], \
                    f"grab {box} outside the {frame.shape[1]}x{frame.shape[0]} fake screen"
                return _Shot(frame[t:t + h, l:l + w])

        return _MSS()
