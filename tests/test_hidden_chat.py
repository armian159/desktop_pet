"""A chat that is in flight while the pet is hidden must stay hidden and must not get stuck."""

import pytest
from PySide6.QtCore import QRect
from PySide6.QtTest import QSignalSpy, QTest

from phoebe_pet.app import PetApp, bounds_of
from phoebe_pet.bubble import BubbleWindow, InputWindow
from phoebe_pet.chat import MSG_OFFLINE, ChatSession
from phoebe_pet.config import Config
from phoebe_pet.pet import Mode
from test_app import FakeWorker

PET = QRect(900, 900, 128, 128)


@pytest.fixture
def state(qapp, pet, win):
    s = PetApp(Config(), pet, win, BubbleWindow(), InputWindow(), ChatSession(Config()), worker_factory=FakeWorker)
    yield s
    s.shutdown()


@pytest.fixture
def bubble(qapp):
    b = BubbleWindow()
    b.follow(PET)
    yield b
    b.close()


def test_suppressed_bubble_collects_text_without_showing(bubble):
    bubble.suppress(True)
    bubble.start()
    bubble.append("안녕")
    assert bubble.text() == "안녕" and not bubble.isVisible()


def test_suppressed_notice_does_not_show(bubble):
    bubble.suppress(True)
    bubble.show_notice("안내")
    assert not bubble.isVisible()


def test_releasing_suppression_shows_what_was_collected_then_hides_on_time(bubble):
    spy = QSignalSpy(bubble.closed)
    bubble.suppress(True)
    bubble.start()
    bubble.append("안녕")
    bubble.finish(delay_ms=20)
    QTest.qWait(80)
    assert spy.count() == 0  # nothing was on screen, so nothing "closed"
    bubble.suppress(False)
    assert bubble.isVisible()
    QTest.qWait(120)
    assert not bubble.isVisible() and spy.count() == 1


def test_releasing_suppression_with_nothing_to_show_stays_hidden(bubble):
    bubble.suppress(True)
    bubble.suppress(False)
    assert not bubble.isVisible()


def test_suppressing_a_visible_bubble_hides_it_without_closing(bubble):
    spy = QSignalSpy(bubble.closed)
    bubble.start()
    bubble.append("hi")
    bubble.suppress(True)
    assert not bubble.isVisible() and spy.count() == 0


def test_reply_streaming_while_hidden_stays_off_screen(state):
    state.input.submitted.emit("안녕")
    state.worker.delta.emit("네")
    state.toggle_hidden()
    state.worker.delta.emit(", 방랑자님")
    assert not state.bubble.isVisible() and state.bubble.text() == "네, 방랑자님"


def test_wait_notice_while_hidden_stays_off_screen(state):
    state.wait_notice_ms = 20
    state.input.submitted.emit("안녕")
    state.toggle_hidden()
    QTest.qWait(120)
    assert not state.bubble.isVisible()


def test_error_while_hidden_stays_off_screen(state):
    state.input.submitted.emit("안녕")
    state.toggle_hidden()
    state.worker.failed.emit(MSG_OFFLINE)
    assert not state.bubble.isVisible()
    state.toggle_hidden()
    assert state.bubble.isVisible() and state.bubble.text() == MSG_OFFLINE


def test_reply_finished_while_hidden_is_shown_on_return_and_chat_ends(state, pet):
    state.input.submitted.emit("안녕")
    state.worker.delta.emit("네")
    state.toggle_hidden()
    state.worker.done.emit("네")
    state.toggle_hidden()
    assert state.bubble.isVisible() and state.bubble.text() == "네"
    assert [m["content"] for m in state.session.history] == ["안녕", "네"]
    state.bubble.closed.emit()
    assert pet.mode is Mode.AUTO


def test_hiding_after_the_reply_is_up_does_not_strand_the_pet(state, pet):
    state.input.submitted.emit("안녕")
    state.worker.delta.emit("네")
    state.worker.done.emit("네")
    state.toggle_hidden()
    state.toggle_hidden()
    state.bubble.finish(delay_ms=10)
    QTest.qWait(100)
    assert pet.mode is Mode.AUTO


def test_follow_screen_moves_the_pet_into_that_screen(state, pet, qapp):
    screen = qapp.primaryScreen()
    state.follow_screen(screen)
    b = bounds_of(screen)
    v = pet.tick(0.0, (-9999, -9999))
    assert b.left <= v.x <= b.right - 128 and b.top <= v.y <= b.bottom - 128
