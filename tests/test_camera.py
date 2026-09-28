from types import SimpleNamespace

import pytest

import lib.camera as camera


@pytest.fixture
def clicks(monkeypatch):
    log = []
    monkeypatch.setattr(camera, "hesitate", lambda: None)
    monkeypatch.setattr(camera.time, "sleep", lambda s: None)
    monkeypatch.setattr(camera, "jitter", lambda x, y, n=5: (x, y))
    monkeypatch.setattr(camera, "human_click", lambda x, y: log.append(("left", x, y)))
    monkeypatch.setattr(camera, "human_right_click", lambda x, y: (log.append(("right", x, y)), (x + 1, y + 2))[1])
    monkeypatch.setattr(camera, "menu_click", lambda x, y: log.append(("menu", x, y)))
    return log


CFG = SimpleNamespace(COMPASS=(100, 50), MENU_HEADER=19, MENU_ROW_H=15,
                      LOOK_WEST_ROW=3, LOOK_SOUTH_ROW=2)


def test_west_clicks_look_west_row(clicks):
    camera.face("west", CFG)
    # menu opens at (101, 52): x + 5, y + header + row*h + h//2
    assert clicks == [("right", 100, 50), ("menu", 106, 52 + 19 + 3 * 15 + 7)]


def test_south_uses_its_own_row(clicks):
    camera.face("south", CFG)
    assert clicks[-1] == ("menu", 106, 52 + 19 + 2 * 15 + 7)


def test_north_left_clicks_compass_without_menu(clicks):
    camera.face("north", CFG)
    assert clicks == [("left", 100, 50)]


def test_unknown_direction_raises(clicks):
    with pytest.raises(ValueError):
        camera.face("up", CFG)


def test_missing_row_constant_raises(clicks):
    with pytest.raises(AttributeError):
        camera.face("east", CFG)
