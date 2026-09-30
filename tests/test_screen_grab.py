"""screen.grab offsets: monitor-relative by default, absolute on request."""
from lib.screen import grab
from tests.fakescreen import canvas, paint


def test_grab_is_monitor_relative_by_default(fake_screen):
    fake_screen.monitor = (10, 0)
    fake_screen.show(paint(canvas(100, 100), 10, 0, 1, 1, (255, 255, 255)))
    frame, offset = grab((0, 0, 5, 5))
    assert offset == (10, 0) and frame[0, 0].tolist() == [255, 255, 255]


def test_grab_absolute_ignores_monitor_origin(fake_screen):
    # movement and get_pixel_color have always captured absolute coordinates
    fake_screen.monitor = (10, 0)
    fake_screen.show(paint(canvas(100, 100), 10, 0, 1, 1, (255, 255, 255)))
    frame, offset = grab((0, 0, 5, 5), absolute=True)
    assert offset == (0, 0) and frame[0, 0].tolist() == [0, 0, 0]
