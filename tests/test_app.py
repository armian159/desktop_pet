import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtTest import QTest

from phoebe_pet.app import PetApp
from phoebe_pet.bubble import BubbleWindow, InputWindow
from phoebe_pet.chat import MSG_OFFLINE, ChatSession
from phoebe_pet.config import Config
from phoebe_pet.pet import Mode


class FakeWorker(QObject):
    delta = Signal(str)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, url, payload, model):
        super().__init__()
        self.payload = payload
        self.started = False

    def start(self):
        self.started = True

    def requestInterruption(self):
        pass

    def isRunning(self):
        return False

    def wait(self, *_):
        return True


@pytest.fixture
def session():
    return ChatSession(Config())


@pytest.fixture
def app_state(qapp, pet, win, session):
    state = PetApp(Config(), pet, win, BubbleWindow(), InputWindow(), session, worker_factory=FakeWorker)
    yield state
    state.shutdown()


def test_double_click_opens_input(app_state, win):
    win.double_clicked.emit()
    assert app_state.input.isVisible()


def test_submit_starts_thinking_and_a_request(app_state, pet):
    app_state.input.submitted.emit("안녕")
    assert pet.mode is Mode.THINK and app_state.worker.started
    assert app_state.worker.payload["messages"][-1] == {"role": "user", "content": "안녕"}


def test_first_delta_starts_talking_and_fills_bubble(app_state, pet):
    app_state.input.submitted.emit("안녕")
    app_state.worker.delta.emit("네, ")
    app_state.worker.delta.emit("방랑자님")
    assert pet.mode is Mode.TALK and app_state.bubble.text() == "네, 방랑자님"


def test_done_records_turn_and_pet_resumes_when_bubble_closes(app_state, pet, session):
    app_state.input.submitted.emit("안녕")
    app_state.worker.delta.emit("네")
    app_state.worker.done.emit("네")
    assert [m["content"] for m in session.history] == ["안녕", "네"]
    assert pet.mode is Mode.TALK
    app_state.bubble.closed.emit()
    assert pet.mode is Mode.AUTO


def test_failure_shows_notice_and_keeps_history_clean(app_state, pet, session):
    app_state.input.submitted.emit("안녕")
    app_state.worker.failed.emit(MSG_OFFLINE)
    assert app_state.bubble.text() == MSG_OFFLINE and session.history == [] and not session.busy
    assert pet.mode is Mode.AUTO


def test_second_submit_while_busy_is_ignored(app_state):
    app_state.input.submitted.emit("하나")
    first = app_state.worker
    app_state.input.submitted.emit("둘")
    assert app_state.worker is first


def test_new_question_while_old_bubble_is_up_keeps_thinking(app_state, pet):
    app_state.input.submitted.emit("하나")
    app_state.worker.delta.emit("답")
    app_state.worker.done.emit("답")
    app_state.input.submitted.emit("둘")
    app_state.bubble.closed.emit()  # the old bubble hiding must not end the new chat
    assert pet.mode is Mode.THINK


def test_slow_first_token_shows_waiting_notice(app_state):
    app_state.wait_notice_ms = 20
    app_state.input.submitted.emit("안녕")
    QTest.qWait(120)
    assert "생각" in app_state.bubble.text()


def test_bubble_follows_the_pet(app_state, win, pet):
    app_state.bubble.show_notice("hi")
    before = app_state.bubble.pos()
    pet._place_on_wall(left=True, y=300)
    win.step()
    assert app_state.bubble.pos() != before
