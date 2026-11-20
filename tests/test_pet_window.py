from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QSignalSpy, QTest

from phoebe_pet.pet import Mode
from phoebe_pet.pet_window import FAST_MS, SLOW_MS

MID = QPoint(64, 90)


def test_window_flags(win):
    f = win.windowFlags()
    assert f & Qt.FramelessWindowHint and f & Qt.WindowStaysOnTopHint
    assert (f & Qt.Tool) == Qt.Tool and f & Qt.WindowDoesNotAcceptFocus
    assert win.testAttribute(Qt.WA_TranslucentBackground)
    assert win.testAttribute(Qt.WA_ShowWithoutActivating)


def test_size_matches_sprites(win, sprites):
    assert win.size() == sprites.size


def test_window_sits_where_the_pet_is(win, pet):
    view = pet.tick(0.0, (-9999, -9999))
    assert (win.x(), win.y()) == (view.x, view.y)


def test_wall_offset_shifts_the_window(win, pet):
    pet._place_on_wall(left=True, y=300)
    win.step()
    assert (win.x(), win.y()) == (-64, 300)


def test_timer_slows_when_resting(win, pet):
    pet._start("sit")
    win.step()
    assert win.timer.interval() == SLOW_MS
    pet._start("walk")
    win.step()
    assert win.timer.interval() == FAST_MS


def test_press_without_move_is_not_a_drag(win, pet):
    QTest.mousePress(win, Qt.LeftButton, pos=MID)
    QTest.mouseRelease(win, Qt.LeftButton, pos=MID)
    assert pet.mode is Mode.AUTO


def test_small_wobble_is_not_a_drag(win, pet):
    QTest.mousePress(win, Qt.LeftButton, pos=MID)
    QTest.mouseMove(win, MID + QPoint(2, 1))
    assert pet.mode is Mode.AUTO
    QTest.mouseRelease(win, Qt.LeftButton, pos=MID + QPoint(2, 1))


def test_press_and_move_starts_drag_and_release_throws(win, pet):
    QTest.mousePress(win, Qt.LeftButton, pos=MID)
    QTest.mouseMove(win, MID + QPoint(20, 0))
    assert pet.mode is Mode.DRAGGED and win.timer.interval() == FAST_MS
    QTest.mouseRelease(win, Qt.LeftButton, pos=MID + QPoint(20, 0))
    assert pet.mode is Mode.AIR


def test_double_click_emits_and_does_not_drag(win, pet):
    spy = QSignalSpy(win.double_clicked)
    QTest.mouseDClick(win, Qt.LeftButton, pos=MID)
    assert spy.count() == 1 and pet.mode is Mode.AUTO


def test_right_button_does_not_drag(win, pet):
    QTest.mousePress(win, Qt.RightButton, pos=MID)
    QTest.mouseMove(win, MID + QPoint(30, 0))
    assert pet.mode is Mode.AUTO
    QTest.mouseRelease(win, Qt.RightButton, pos=MID + QPoint(30, 0))


def test_transparent_pixels_are_masked_out(win):
    assert not win.mask().contains(QPoint(0, 0))
    assert win.mask().contains(MID)


def test_moved_signal_reports_geometry(win, pet):
    spy = QSignalSpy(win.moved)
    pet._place_on_wall(left=False, y=200)
    win.step()
    assert spy.count() >= 1
