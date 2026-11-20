import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtTest import QSignalSpy, QTest

from phoebe_pet.bubble import BubbleWindow, InputWindow

PET = QRect(900, 900, 128, 128)


@pytest.fixture
def bubble(qapp):
    b = BubbleWindow()
    b.follow(PET)
    yield b
    b.close()


@pytest.fixture
def inp(qapp):
    w = InputWindow()
    w.open_at(PET)
    yield w
    w.close()


def test_bubble_never_takes_focus(bubble):
    assert bubble.windowFlags() & Qt.WindowDoesNotAcceptFocus
    assert bubble.testAttribute(Qt.WA_ShowWithoutActivating)


def test_append_accumulates_and_shows(bubble):
    bubble.start()
    bubble.append("안")
    bubble.append("녕")
    assert bubble.text() == "안녕" and bubble.isVisible()


def test_start_clears_previous_text(bubble):
    bubble.start()
    bubble.append("old")
    bubble.start()
    assert bubble.text() == ""


def test_long_text_switches_to_scroll_mode(bubble):
    bubble.start()
    bubble.append("짧은 말")
    assert not bubble.is_scroll_mode()
    bubble.append("가" * 300)
    assert bubble.is_scroll_mode()


def test_bubble_stays_above_pet_as_it_grows(bubble):
    bubble.start()
    bubble.append("가나다라마바사 " * 12)
    assert bubble.geometry().bottom() < PET.top()


def test_click_copies_text(bubble, qapp):
    bubble.start()
    bubble.append("복사")
    bubble.finish()
    QTest.mouseClick(bubble, Qt.LeftButton)
    assert qapp.clipboard().text() == "복사"


def test_short_bubble_hides_itself_and_reports(bubble, qapp):
    spy = QSignalSpy(bubble.closed)
    bubble.start()
    bubble.append("hi")
    bubble.finish(delay_ms=20)
    QTest.qWait(120)
    assert not bubble.isVisible() and spy.count() == 1


def test_long_bubble_stays_until_closed(bubble):
    spy = QSignalSpy(bubble.closed)
    bubble.start()
    bubble.append("가" * 300)
    bubble.finish(delay_ms=20)
    QTest.qWait(120)
    assert bubble.isVisible() and spy.count() == 0
    bubble.close_button.click()
    assert not bubble.isVisible() and spy.count() == 1


def test_long_bubble_copy_button(bubble, qapp):
    bubble.start()
    bubble.append("x = 1\n" * 10)
    bubble.copy_button.click()
    assert qapp.clipboard().text() == "x = 1\n" * 10


def test_new_text_cancels_pending_hide(bubble):
    bubble.start()
    bubble.append("a")
    bubble.finish(delay_ms=30)
    bubble.start()
    bubble.append("b")
    QTest.qWait(120)
    assert bubble.isVisible()


def test_notice_shows_text(bubble):
    bubble.show_notice("안내")
    assert bubble.text() == "안내" and bubble.isVisible()


def test_input_enter_submits_and_closes(inp):
    spy = QSignalSpy(inp.submitted)
    QTest.keyClicks(inp.edit, "hi")
    QTest.keyClick(inp.edit, Qt.Key_Return)
    assert spy.count() == 1 and spy.at(0)[0] == "hi" and not inp.isVisible()
    assert inp.edit.toPlainText() == ""


def test_input_escape_closes_without_submit(inp):
    spy = QSignalSpy(inp.submitted)
    QTest.keyClicks(inp.edit, "hi")
    QTest.keyClick(inp.edit, Qt.Key_Escape)
    assert spy.count() == 0 and not inp.isVisible()


def test_shift_enter_inserts_newline(inp):
    spy = QSignalSpy(inp.submitted)
    QTest.keyClicks(inp.edit, "a")
    QTest.keyClick(inp.edit, Qt.Key_Return, Qt.ShiftModifier)
    assert spy.count() == 0 and "\n" in inp.edit.toPlainText()


def test_empty_enter_does_nothing(inp):
    spy = QSignalSpy(inp.submitted)
    QTest.keyClick(inp.edit, Qt.Key_Return)
    assert spy.count() == 0 and inp.isVisible()
