import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from import_sheet import import_sheet, parse_names  # noqa: E402

GREEN = (0, 255, 0)
RED = (220, 30, 30)
CELL = 200


def make_sheet(path, cols, rows, draw_cells, bg=GREEN, mode="RGB"):
    fill = bg if mode == "RGB" else (0, 0, 0, 0)
    sheet = Image.new(mode, (cols * CELL, rows * CELL), fill)
    d = ImageDraw.Draw(sheet)
    for index, box in draw_cells.items():
        ox, oy = (index % cols) * CELL, (index // cols) * CELL
        l, t, r, b = box
        d.rectangle((ox + l, oy + t, ox + r - 1, oy + b - 1), fill=RED)
    sheet.save(path)
    return path


def box(path):
    return Image.open(path).convert("RGBA").getchannel("A").point(lambda a: 255 if a > 128 else 0).getbbox()


@pytest.fixture
def sheet(tmp_path):
    cells = {
        0: (70, 40, 130, 160),  # stand: 60 wide, 120 tall
        1: (10, 10, 70, 70),  # sit: 60 x 60, drawn off-centre
        2: (80, 50, 120, 150),  # wall: 40 x 100
        3: (75, 60, 125, 140),  # ceiling: 50 x 80
    }
    return make_sheet(tmp_path / "sheet.png", 2, 2, cells)


def run(sheet, tmp_path, names="1,11,13,23", **kw):
    out = tmp_path / "out"
    written = import_sheet(sheet, out, cols=2, rows=2, names=parse_names(names, 4), **kw)
    return out, written


def test_writes_named_square_rgba_frames(sheet, tmp_path):
    out, written = run(sheet, tmp_path)
    assert sorted(p.name for p in written) == ["shime1.png", "shime11.png", "shime13.png", "shime23.png"]
    for p in written:
        img = Image.open(p)
        assert img.size == (128, 128) and img.mode == "RGBA"


def test_background_becomes_transparent_and_none_is_left(sheet, tmp_path):
    out, _ = run(sheet, tmp_path)
    img = Image.open(out / "shime1.png")
    assert img.getpixel((0, 0))[3] == 0 and img.getpixel((127, 0))[3] == 0
    px = np.asarray(img).astype(int)
    assert not ((px[..., 3] > 0) & (px[..., 1] > 200) & (px[..., 0] < 80)).any()


def test_standing_frame_has_feet_on_the_bottom_centre(sheet, tmp_path):
    out, _ = run(sheet, tmp_path)
    l, t, r, b = box(out / "shime1.png")
    assert b == 128 and abs((l + r) / 2 - 64) <= 1.5


def test_all_frames_share_one_scale(sheet, tmp_path):
    out, _ = run(sheet, tmp_path)
    stand, sit = box(out / "shime1.png"), box(out / "shime11.png")
    stand_h, sit_h = stand[3] - stand[1], sit[3] - sit[1]
    assert 110 <= stand_h <= 120  # the tallest pose nearly fills the frame
    assert abs(sit_h - stand_h / 2) <= 3 and sit[3] == 128


def test_wall_frame_sits_right_of_the_centre_line(sheet, tmp_path):
    out, _ = run(sheet, tmp_path)
    l, _t, _r, b = box(out / "shime13.png")
    assert abs(l - 64) <= 2 and b == 128


def test_ceiling_frame_hangs_from_y48(sheet, tmp_path):
    out, _ = run(sheet, tmp_path)
    l, t, r, _b = box(out / "shime23.png")
    assert abs(t - 48) <= 2 and abs((l + r) / 2 - 64) <= 1.5


def test_dragged_frame_hangs_from_the_top(tmp_path, sheet):
    out, _ = run(sheet, tmp_path, names="1,7,-,-")
    assert box(out / "shime7.png")[1] <= 1


def test_skipped_cells_write_nothing(sheet, tmp_path):
    out, written = run(sheet, tmp_path, names="1,-,-,23")
    assert sorted(p.name for p in written) == ["shime1.png", "shime23.png"]


def test_empty_cell_is_skipped_not_fatal(tmp_path):
    path = make_sheet(tmp_path / "s.png", 2, 2, {0: (70, 40, 130, 160)})
    out, written = run(path, tmp_path, names="1,2,3,4")
    assert [p.name for p in written] == ["shime1.png"]


def test_background_colour_enclosed_by_the_character_is_kept(tmp_path):
    path = tmp_path / "ring.png"
    img = Image.new("RGB", (CELL, CELL), GREEN)
    d = ImageDraw.Draw(img)
    d.rectangle((50, 30, 149, 169), fill=RED)
    d.rectangle((80, 70, 119, 129), fill=GREEN)  # e.g. green eyes or clothes
    img.save(path)
    out = tmp_path / "out"
    import_sheet(path, out, cols=1, rows=1, names=["shime1"])
    assert Image.open(out / "shime1.png").getpixel((64, 70))[3] == 255


def test_sheet_that_is_already_transparent_is_used_as_is(tmp_path):
    path = make_sheet(tmp_path / "t.png", 2, 2, {0: (70, 40, 130, 160)}, mode="RGBA")
    out, written = run(path, tmp_path, names="1,-,-,-")
    l, t, r, b = box(out / "shime1.png")
    assert b == 128 and Image.open(out / "shime1.png").getpixel((64, 100))[:3] == RED


def test_explicit_background_colour(tmp_path):
    path = make_sheet(tmp_path / "m.png", 2, 2, {0: (70, 40, 130, 160)}, bg=(255, 0, 255))
    out, _ = run(path, tmp_path, names="1,-,-,-", bg="#ff00ff")
    assert Image.open(out / "shime1.png").getpixel((2, 2))[3] == 0


def test_custom_size(sheet, tmp_path):
    out, _ = run(sheet, tmp_path, size=256)
    assert Image.open(out / "shime1.png").size == (256, 256)
    assert abs(box(out / "shime23.png")[1] - 96) <= 3


def test_preview_sheet_is_written(sheet, tmp_path):
    out, _ = run(sheet, tmp_path)
    assert (out / "_preview.png").is_file()


def test_parse_names():
    assert parse_names("1, 2,-,talk1", 4) == ["shime1", "shime2", None, "talk1"]
    assert parse_names("1,2", 4) == ["shime1", "shime2", None, None]


@pytest.mark.parametrize("spec", ["1,2,3,4,5", "0", "47", "walk", "1,1"])
def test_parse_names_rejects_bad_input(spec):
    with pytest.raises(ValueError):
        parse_names(spec, 4)
