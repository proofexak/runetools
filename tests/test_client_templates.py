import json

import numpy as np
from PIL import Image

import lib.client_templates_editor as ed
from tests.fakescreen import canvas, paint


def test_save_template_writes_exact_crop(fake_screen, tmp_path):
    fake_screen.show(paint(canvas(400, 400), 120, 80, 40, 20, (200, 30, 10)))
    ed.save_template("login_play", (110, 70, 60, 40), directory=str(tmp_path))
    png = np.array(Image.open(tmp_path / "login_play.png").convert("RGB"))
    assert png.shape == (40, 60, 3)
    assert png[15, 15].tolist() == [200, 30, 10]          # inside the painted button, RGB
    assert png[0, 0].tolist() == [0, 0, 0]
    assert json.loads((tmp_path / "regions.json").read_text())["login_play"] == [110, 70, 60, 40]


def test_recapture_overwrites(fake_screen, tmp_path):
    fake_screen.show(canvas(400, 400, (10, 10, 10)))
    ed.save_template("in_game", (0, 0, 10, 10), directory=str(tmp_path))
    fake_screen.show(canvas(400, 400, (90, 90, 90)))
    ed.save_template("in_game", (0, 0, 20, 5), directory=str(tmp_path))
    png = np.array(Image.open(tmp_path / "in_game.png").convert("RGB"))
    assert png.shape == (5, 20, 3) and png[0, 0].tolist() == [90, 90, 90]


def test_fields_cover_all_templates():
    import lib.client as client
    assert {f[2] for f in ed.FIELDS} == set(client.REQUIRED) | set(client.OPTIONAL)
    assert all(f[3] == "region" for f in ed.FIELDS)


def test_save_template_crops_from_the_pre_overlay_snapshot(fake_screen, tmp_path):
    # In Xvfb the capture overlay is opaque black, so the live screen after the
    # drag is useless; the crop must come from the snapshot taken before it.
    snapshot = paint(canvas(400, 400), 120, 80, 40, 20, (200, 30, 10))
    fake_screen.show(canvas(400, 400))                       # what a live grab would see now
    ed.save_template("login_play", (110, 70, 60, 40), directory=str(tmp_path), snapshot=snapshot)
    png = np.array(Image.open(tmp_path / "login_play.png").convert("RGB"))
    assert png[15, 15].tolist() == [200, 30, 10]


def test_snapshot_screen_grabs_the_whole_display(fake_screen):
    from lib.config_editor import snapshot_screen
    fake_screen.show(paint(canvas(400, 400), 0, 0, 1, 1, (1, 2, 3)))
    frame = snapshot_screen()
    assert frame.shape == (400, 400, 3) and frame[0, 0].tolist() == [3, 2, 1]   # BGR


def test_polygon_value_is_rejected_cleanly(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        ed.save_template("in_game", [(0, 0), (5, 0), (0, 5)], directory=str(tmp_path))
