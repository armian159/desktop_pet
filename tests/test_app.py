import random
from datetime import datetime

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtTest import QTest

from phoebe_pet.app import PetApp
from phoebe_pet.bubble import BubbleWindow, InputWindow
from phoebe_pet.chat import MSG_OFFLINE, ChatSession
from phoebe_pet.config import Config
from phoebe_pet.mood import Mood
from phoebe_pet.pet import Mode
from phoebe_pet.speech import Speaker


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


# ---- menu, hiding -------------------------------------------------

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


# ---- speaking up on its own ---------------------------------------------------

NOW = datetime(2026, 11, 20, 10, 0)
LINES = {"calm": ("평온한 말",), "thrown": ("앗!",), "bored": ("심심해요",), "happy": ("좋아요",)}


def make_live(pet, win, session, monologue):
    pet.mood = Mood(NOW)  # a calm 10 a.m. mood, whatever the real clock says
    pet.force("stand")
    speaker = Speaker(LINES, random.Random(0), (1, 1), NOW)
    return PetApp(
        Config(monologue=monologue), pet, win, BubbleWindow(), InputWindow(), session,
        worker_factory=FakeWorker, speaker=speaker, now=lambda: NOW,
    )


@pytest.fixture
def app_live(qapp, pet, win, session):
    state = make_live(pet, win, session, True)
    yield state
    state.shutdown()


@pytest.fixture
def app_live_off(qapp, pet, win, session):
    state = make_live(pet, win, session, False)
    yield state
    state.shutdown()


def test_speaks_after_gap_with_situation_prompt(app_live):
    app_live.life_tick(30); assert app_live.speech_worker is None
    app_live.life_tick(40)
    msg = app_live.speech_worker.payload["messages"][-1]
    assert msg["role"] == "user" and msg["content"].startswith("(")


def test_reply_shows_short_bubble_and_records_one_monologue(app_live, session, pet):
    app_live.speak("calm"); app_live.speech_worker.done.emit("구름이 예뻐요. 더 말하면...")
    assert app_live.bubble.text() == "구름이 예뻐요." and not app_live.bubble.is_scroll_mode()
    assert session.history == [{"role": "assistant", "content": "구름이 예뻐요."}] and pet.speaking
    app_live.bubble.closed.emit(); assert not pet.speaking


def test_speech_failure_uses_fallback_silently(app_live):
    app_live.speak("calm"); app_live.speech_worker.failed.emit(MSG_OFFLINE)
    assert app_live.bubble.text() == "평온한 말"


def test_slow_first_token_falls_back_and_late_reply_is_ignored(app_live):
    app_live.first_ms = 10; app_live.speak("calm"); worker = app_live.speech_worker
    QTest.qWait(50); assert app_live.bubble.text() == "평온한 말"
    worker.done.emit("늦은 답"); assert app_live.bubble.text() == "평온한 말"


def test_total_timeout_falls_back(app_live):
    app_live.total_ms = 30; app_live.speak("calm"); app_live.speech_worker.delta.emit("구름")
    QTest.qWait(80); assert app_live.bubble.text() == "평온한 말"


def test_user_chat_abandons_pending_speech(app_live):
    app_live.speak("calm"); speech = app_live.speech_worker
    app_live.input.submitted.emit("안녕"); assert app_live.worker.started
    speech.done.emit("혼잣말"); assert app_live.bubble.text() != "혼잣말"
    assert all(m["content"] != "혼잣말" for m in app_live.session.history)


@pytest.mark.parametrize("block", ["paused", "dragged", "hidden", "input_open", "user_chat_bubble"])
def test_never_speaks_when_it_should_not(app_live, pet, win, block):
    {"paused": lambda: app_live.toggle_pause(),
     "dragged": lambda: pet.grab((500, 300)),
     "hidden": lambda: app_live.toggle_hidden(),
     "input_open": lambda: app_live.input.open_at(win.geometry()),
     "user_chat_bubble": lambda: (app_live.input.submitted.emit("안녕"), app_live.worker.done.emit("네")),
     }[block]()
    app_live.life_tick(120)
    assert app_live.speech_worker is None


def test_monologue_off_changes_mood_but_never_speaks(app_live_off, pet):
    app_live_off.life_tick(3600); assert app_live_off.speech_worker is None and pet.mood.boredom > 0.2


def test_thrown_event_triggers_thrown_line(app_live, pet):
    pet._events.append("thrown"); app_live.life_tick(1); app_live.life_tick(5)
    assert app_live.speech_worker is not None
    app_live.speech_worker.failed.emit("x"); assert app_live.bubble.text() == "앗!"


def test_mood_ticks_while_hidden(app_live, pet):
    app_live.toggle_hidden(); before = pet.mood.boredom; app_live.life_tick(600); assert pet.mood.boredom > before


def test_event_cooldown_survives_a_poll_while_waiting_for_the_reply(app_live, pet):
    pet._events.append("thrown"); app_live.life_tick(1); app_live.life_tick(5)
    first = app_live.speech_worker
    app_live.life_tick(1)  # a poll while the reply is still on its way
    first.done.emit("앗, 깜짝이야!"); assert app_live.bubble.text() == "앗, 깜짝이야!"
    app_live.bubble.close_button.click(); assert not app_live.bubble.isVisible() and not pet.speaking
    pet._events.append("thrown"); app_live.life_tick(1); app_live.life_tick(5)
    assert app_live.speech_worker is first


def test_hidden_counts_as_nobody_around_and_awake(app_live, pet):
    pet.force("lie"); pet.mouse_near = True
    app_live.toggle_hidden()
    boredom, energy = pet.mood.boredom, pet.mood.energy
    app_live.life_tick(600)
    assert pet.mood.boredom > boredom and pet.mood.energy < energy
