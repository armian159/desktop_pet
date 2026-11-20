import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage

from phoebe_pet.frames import SpriteError
from phoebe_pet.sprites import SpriteSet


def save(folder, name, w, h, paint=None):
    img = QImage(w, h, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    if paint:
        paint(img)
    assert img.save(str(folder / f"{name}.png"))


def left_half_red(img):
    for x in range(img.width() // 2):
        for y in range(img.height()):
            img.setPixelColor(x, y, QColor(255, 0, 0))


def test_missing_shime1_raises(tmp_path, qapp):
    with pytest.raises(SpriteError):
        SpriteSet(tmp_path, 1.0)


def test_scale_and_mixed_sizes(tmp_path, qapp):
    save(tmp_path, "shime1", 128, 128)
    save(tmp_path, "shime2", 64, 200)
    s = SpriteSet(tmp_path, 0.5)
    assert (s.size.width(), s.size.height()) == (64, 64)
    assert s.pixmap("shime2", False).size() == s.size


def test_facing_right_is_mirrored(tmp_path, qapp):
    save(tmp_path, "shime1", 128, 128, left_half_red)
    s = SpriteSet(tmp_path, 1.0)
    assert s.pixmap("shime1", False).toImage().pixelColor(20, 64).red() == 255
    assert s.pixmap("shime1", True).toImage().pixelColor(100, 64).red() == 255
    assert s.pixmap("shime1", True).toImage().pixelColor(20, 64).alpha() == 0


def test_missing_frame_uses_fallback(tmp_path, qapp):
    save(tmp_path, "shime1", 128, 128, left_half_red)
    s = SpriteSet(tmp_path, 1.0)
    assert s.pixmap("shime33", False).toImage().pixelColor(20, 64).red() == 255


def test_unreadable_png_is_skipped(tmp_path, qapp):
    save(tmp_path, "shime1", 128, 128)
    (tmp_path / "shime2.png").write_bytes(b"not a png")
    s = SpriteSet(tmp_path, 1.0)
    assert s.pixmap("shime2", False).size() == s.size
