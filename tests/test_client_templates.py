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
