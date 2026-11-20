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


# ---- menu, hiding, monologue -------------------------------------------------

from phoebe_pet import fullscreen  # noqa: E402


@pytest.fixture
def menu(app_state):
    return app_state.menu


def find(menu, text):
    return next(a for a in menu.actions() if a.text() == text)


def test_menu_items(menu):
    assert [a.text() for a in menu.actions() if not a.isSeparator()] == ["일시정지", "대화 초기화", "숨기기", "개발자 패널", "종료"]


def test_pause_toggles_pet_and_label(menu, pet):
    act = menu.actions()[0]
    act.trigger()
    assert pet.mode is Mode.PAUSED and act.text() == "다시 움직이기"
    act.trigger()
    assert pet.mode is Mode.AUTO and act.text() == "일시정지"


def test_reset_clears_history(menu, session):
    session.begin("a")
    session.succeed("A")
    find(menu, "대화 초기화").trigger()
    assert session.history == []


def test_hide_and_show(menu, win):
    act = find(menu, "숨기기")
    act.trigger()
    assert not win.isVisible() and act.text() == "보이기"
    act.trigger()
    assert win.isVisible()


def test_hidden_pet_stops_ticking(menu, win):
    find(menu, "숨기기").trigger()
    assert not win.timer.isActive()
    find(menu, "보이기").trigger()
    assert win.timer.isActive()


def test_fullscreen_hides_and_restores(app_state, win, monkeypatch):
    monkeypatch.setattr(fullscreen, "foreground_is_fullscreen", lambda: True)
    app_state.poll()
    assert not win.isVisible()
    monkeypatch.setattr(fullscreen, "foreground_is_fullscreen", lambda: False)
    app_state.poll()
    assert win.isVisible()


def test_fullscreen_does_not_override_manual_hide(app_state, win, menu, monkeypatch):
    find(menu, "숨기기").trigger()
    monkeypatch.setattr(fullscreen, "foreground_is_fullscreen", lambda: False)
    app_state.poll()
    assert not win.isVisible()


def test_right_click_pops_up_the_menu(app_state, win, menu):
    from PySide6.QtCore import QPoint

    win.context_requested.emit(QPoint(300, 300))
    assert menu.isVisible()
    menu.hide()


def test_monologue_off_by_default_never_fires(app_state):
    app_state.idle_tick(seconds=3600)
    assert app_state.worker is None


@pytest.fixture
def app_state_monologue_on(qapp, pet, win, session):
    state = PetApp(Config(monologue=True), pet, win, BubbleWindow(), InputWindow(), session, worker_factory=FakeWorker)
    yield state
    state.shutdown()


def test_monologue_fires_after_long_quiet(app_state_monologue_on):
    app_state_monologue_on.idle_tick(seconds=60)
    assert app_state_monologue_on.worker is None
    app_state_monologue_on.idle_tick(seconds=3600)
    assert app_state_monologue_on.worker.started


def test_monologue_not_stored_as_user_turn(app_state_monologue_on, session):
    app_state_monologue_on.idle_tick(seconds=3600)
    app_state_monologue_on.worker.delta.emit("오늘 하늘이 맑네요.")
    app_state_monologue_on.worker.done.emit("오늘 하늘이 맑네요.")
    assert session.history == [{"role": "assistant", "content": "오늘 하늘이 맑네요."}]


def test_user_cannot_start_a_second_request_during_monologue(app_state_monologue_on):
    app_state_monologue_on.idle_tick(seconds=3600)
    first = app_state_monologue_on.worker
    app_state_monologue_on.input.submitted.emit("안녕")
    assert app_state_monologue_on.worker is first


def test_interaction_resets_the_quiet_clock(app_state_monologue_on, pet):
    app_state_monologue_on.monologue_after = 900
    app_state_monologue_on.idle_tick(seconds=800)
    pet.tick(0.05, (-9999, -9999))
    app_state_monologue_on.idle_tick(seconds=1)
    pet.touch()
    app_state_monologue_on.idle_tick(seconds=800)
    app_state_monologue_on.idle_tick(seconds=50)
    assert app_state_monologue_on.worker is None


def test_character_folder_can_bring_its_own_actions(tmp_path):
    from phoebe_pet.app import actions_file

    (tmp_path / "assets" / "plain").mkdir(parents=True)
    (tmp_path / "assets" / "fancy").mkdir(parents=True)
    own = tmp_path / "assets" / "fancy" / "actions.toml"
    own.write_text("", encoding="utf-8")
    assert actions_file(tmp_path, "plain") == tmp_path / "actions.toml"
    assert actions_file(tmp_path, "fancy") == own


def test_menu_opens_the_developer_panel(app_state, menu):
    items = {a.text(): a for a in menu.actions()}
    assert "개발자 패널" in items
    items["개발자 패널"].trigger()
    assert app_state.dev_panel.isVisible()
    app_state.dev_panel.buttons["sit"].click()
    assert app_state.pet.action == "sit"
    app_state.dev_panel.close()
