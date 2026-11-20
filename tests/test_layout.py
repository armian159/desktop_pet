from PySide6.QtCore import QPoint, QRect, QSize

from phoebe_pet.layout import hide_delay_ms, is_long, place, place_beside

SCREEN = QRect(0, 0, 1920, 1040)


def test_bubble_sits_above_pet_centered():
    p = place(QRect(900, 900, 128, 128), QSize(300, 100), SCREEN)
    assert p == QPoint(900 + 64 - 150, 900 - 100 - 8)


def test_flips_below_when_no_room_above():
    assert place(QRect(900, 0, 128, 128), QSize(300, 100), SCREEN).y() == 128 + 8


def test_clamped_horizontally_at_edges():
    assert place(QRect(0, 900, 128, 128), QSize(300, 100), SCREEN).x() == 0
    assert place(QRect(1792, 900, 128, 128), QSize(300, 100), SCREEN).x() == 1920 - 300


def test_clamped_vertically_when_taller_than_room_either_side():
    assert place(QRect(900, 300, 128, 128), QSize(300, 900), SCREEN).y() == 1040 - 900


def test_beside_prefers_right_then_left():
    assert place_beside(QRect(900, 900, 128, 128), QSize(280, 60), SCREEN).x() == 900 + 128 + 8
    assert place_beside(QRect(1792, 900, 128, 128), QSize(280, 60), SCREEN).x() == 1792 - 280 - 8


def test_beside_stays_on_screen_vertically():
    assert place_beside(QRect(900, 1000, 128, 128), QSize(280, 60), SCREEN).y() == 1040 - 60


def test_is_long():
    assert not is_long("안녕하세요, 방랑자님.")
    assert is_long("가" * 201) and is_long("a\n" * 7) and is_long("```py\nx\n```")


def test_hide_delay_bounds():
    assert hide_delay_ms("") == 4000 and hide_delay_ms("가" * 50) == 6000 and hide_delay_ms("가" * 9999) == 30000
