"""Builds the pet and its windows, connects them, and runs the Qt event loop."""

from __future__ import annotations

import random
import sys
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QTimer, Slot
from PySide6.QtGui import QIcon, QScreen
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import fullscreen
from .behavior import Chooser, check_complete, load_actions
from .bubble import BubbleWindow, InputWindow
from .chat import ChatSession, ChatWorker
from .config import Config, load_config
from .dev_panel import DevPanel
from .frames import SpriteError
from .personality import Personality, load_personality, personality_file
from .pet import Mode, Pet
from .pet_window import PetWindow
from .physics import Bounds
from .speech import Speaker
from .sprites import SpriteSet

ROOT = Path(__file__).resolve().parents[2]
MSG_WAITING = "잠깐만요, 생각을 정리하고 있어요..."
MSG_NO_REPLY = "음... 뭐라고 해야 할지 모르겠어요."
POLL_MS = 1000

# Where one chat turn stands.
IDLE, WAITING, STREAMING, SHOWING = "idle", "waiting", "streaming", "showing"


def bounds_of(screen: QScreen) -> Bounds:
    g = screen.availableGeometry()
    return Bounds(g.left(), g.top(), g.left() + g.width(), g.top() + g.height())


def actions_file(root: Path, character: str) -> Path:
    """A character folder may carry its own actions.toml (e.g. longer animations)."""
    own = root / "assets" / character / "actions.toml"
    return own if own.is_file() else root / "actions.toml"


class PetApp(QObject):
    """Glue between the pet, its windows, the menu and the chat session."""

    def __init__(
        self,
        cfg: Config,
        pet: Pet,
        window: PetWindow,
        bubble: BubbleWindow,
        input: InputWindow,
        session: ChatSession,
        worker_factory=ChatWorker,
        speaker: Speaker | None = None,
        clock=time.monotonic,
        now=datetime.now,
    ) -> None:
        super().__init__()
        self.cfg = cfg
        self.pet = pet
        self.window = window
        self.bubble = bubble
        self.input = input
        self.session = session
        self.worker = None
        self.wait_notice_ms = 8000
        self.speaker = speaker or Speaker(
            Personality({}, {}).lines, random.Random(), cfg.monologue_minutes, now()
        )
        self.speech_worker = None
        self.first_ms = 6000  # no first token by then: say a stock line instead
        self.total_ms = 15000  # no full reply by then: same
        self._worker_factory = worker_factory
        self._clock = clock
        self._now = now
        self._last_poll = clock()
        self._phase = IDLE
        self._speech_count = 0
        self._speech_live: int | None = None  # the request whose reply is still wanted
        self._speech_key = ""
        self._user_hidden = False
        self._fullscreen_hidden = False
        self._tray: QSystemTrayIcon | None = None
        self._screen: QScreen | None = None
        self.dev_panel: DevPanel | None = None
        self._wait_timer = QTimer(self)
        self._wait_timer.setSingleShot(True)
        self._wait_timer.timeout.connect(self._on_slow)
        self._first_timer = QTimer(self)
        self._first_timer.setSingleShot(True)
        self._first_timer.timeout.connect(self._on_speech_timeout)
        self._total_timer = QTimer(self)
        self._total_timer.setSingleShot(True)
        self._total_timer.timeout.connect(self._on_speech_timeout)
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self.poll)
        self.menu = self._build_menu()
        window.double_clicked.connect(self.open_input)
        window.context_requested.connect(self._show_menu)
        window.moved.connect(bubble.follow)
        input.submitted.connect(self.submit)
        bubble.closed.connect(self._on_bubble_closed)
        bubble.follow(window.geometry())

    # ---- menu ---------------------------------------------------------------

    def _build_menu(self) -> QMenu:
        menu = QMenu()
        self._pause_action = menu.addAction("일시정지", self.toggle_pause)
        menu.addAction("대화 초기화", self.reset_chat)
        self._hide_action = menu.addAction("숨기기", self.toggle_hidden)
        menu.addAction("개발자 패널", self.open_dev_panel)
        menu.addSeparator()
        menu.addAction("종료", QApplication.quit)
        return menu

    @Slot()
    def open_dev_panel(self) -> None:
        if self.dev_panel is None:
            self.dev_panel = DevPanel(self.pet)
        self.dev_panel.show()
        self.dev_panel.raise_()

    @Slot(QPoint)
    def _show_menu(self, pos: QPoint) -> None:
        self.menu.popup(pos)

    def start_background(self, icon: QIcon) -> None:
        """Tray icon and the once-a-second housekeeping; not used in tests."""
        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip("페비")
        self._tray.setContextMenu(self.menu)
        self._tray.show()
        self._poll_timer.start(POLL_MS)

    @Slot()
    def toggle_pause(self) -> None:
        paused = self._pause_action.text() == "일시정지"
        self.pet.set_paused(paused)
        self._pause_action.setText("다시 움직이기" if paused else "일시정지")

    @Slot()
    def reset_chat(self) -> None:
        self.session.reset()

    @Slot()
    def toggle_hidden(self) -> None:
        self._user_hidden = not self._user_hidden
        self._hide_action.setText("보이기" if self._user_hidden else "숨기기")
        self._apply_visibility()

    def _apply_visibility(self) -> None:
        visible = not (self._user_hidden or self._fullscreen_hidden)
        if visible == self.window.isVisible():
            return
        # A chat may be in flight; the bubble keeps collecting it out of sight
        # and shows it when the pet comes back.
        self.bubble.suppress(not visible)
        if visible:
            self.window.show()
            self.window.timer.start()
        else:
            self.window.timer.stop()
            self.window.hide()
            self.input.hide()

    def follow_screen(self, screen: QScreen) -> None:
        """Live on `screen`: track its work area, now and when it changes."""
        if self._screen is not None:
            try:
                self._screen.availableGeometryChanged.disconnect(self._on_work_area_changed)
            except (RuntimeError, TypeError):  # the old screen is already gone
                pass
        self._screen = screen
        screen.availableGeometryChanged.connect(self._on_work_area_changed)
        self._on_work_area_changed()

    @Slot()
    def _on_work_area_changed(self, *_args) -> None:
        if self._screen is not None:
            self.pet.set_bounds(bounds_of(self._screen))

    @Slot()
    def poll(self) -> None:
        self._fullscreen_hidden = fullscreen.foreground_is_fullscreen()
        self._apply_visibility()
        clock = self._clock()
        seconds, self._last_poll = clock - self._last_poll, clock
        self.life_tick(seconds)

    # ---- speaking up on its own ------------------------------------------------

    def life_tick(self, seconds: float) -> None:
        """Let mood drift, collect what just happened, and speak up when a line is due."""
        pet, speaker = self.pet, self.speaker
        now = self._now()
        pet.mood.tick(seconds, pet.action, now, pet.mouse_near)
        clock = self._clock()
        events = pet.take_events()
        slot = speaker.clock_event(now)
        if slot is not None:
            events.append(slot)
        for event in events:
            speaker.note_event(event, clock)
        speaker.tick(seconds, pet.mood.name)
        key = speaker.due()
        if key is None:
            return
        if self.can_speak():
            self.speak(key)
        else:
            speaker.drop_pending()  # an event line said later would be stale

    def can_speak(self) -> bool:
        return self._speech_live is None and self._quiet_moment()

    def _quiet_moment(self) -> bool:
        """Nothing is going on that a spontaneous line would get in the way of."""
        return (
            self.cfg.monologue
            and self._phase == IDLE
            and not self.session.busy
            and self.window.isVisible()
            and not self.input.isVisible()
            and not self.bubble.isVisible()
            and self.pet.mode is Mode.AUTO
        )

    def speak(self, key: str) -> None:
        """Ask the model for one line about `key`; a stock line if it is slow or fails."""
        self._abandon_speech()
        self._speech_key = key
        if self.speech_worker is not None and self.speech_worker.isRunning():
            # An abandoned request cannot be cut short; never stack another on top.
            self._speak_fallback()
            return
        pet = self.pet
        situation = self.speaker.situation(
            key, pet.mood.name, pet.action, self._now(), self.speaker.quiet_seconds
        )
        self._speech_count += 1
        rid = self._speech_live = self._speech_count
        worker = self._worker_factory(
            self.cfg.ollama_url,
            self.session.payload([{"role": "user", "content": situation}]),
            self.cfg.model,
        )
        worker.delta.connect(lambda _text, rid=rid: self._on_speech_delta(rid))
        worker.done.connect(lambda reply, rid=rid: self._on_speech_done(rid, reply))
        worker.failed.connect(lambda _message, rid=rid: self._on_speech_failed(rid))
        self.speech_worker = worker
        worker.start()
        self._first_timer.start(self.first_ms)
        self._total_timer.start(self.total_ms)

    def _abandon_speech(self) -> None:
        """Forget the request in flight; whatever it sends back later is ignored."""
        self._speech_live = None
        self._first_timer.stop()
        self._total_timer.stop()

    def _on_speech_delta(self, rid: int) -> None:
        if rid == self._speech_live:
            self._first_timer.stop()

    def _on_speech_done(self, rid: int, reply: str) -> None:
        if rid != self._speech_live:
            return
        self._abandon_speech()
        line = self.speaker.clean(reply)
        if line is None:
            self._speak_fallback()
        else:
            self._show_speech(line)

    def _on_speech_failed(self, rid: int) -> None:
        if rid == self._speech_live:
            self._abandon_speech()
            self._speak_fallback()  # nobody asked; no error notice

    @Slot()
    def _on_speech_timeout(self) -> None:
        if self._speech_live is not None:
            self._abandon_speech()
            self._speak_fallback()

    def _speak_fallback(self) -> None:
        speaker = self.speaker
        line = speaker.fallback(self._speech_key) or speaker.fallback(self.pet.mood.name)
        if line is None:
            self._skip_speech()
        else:
            self._show_speech(line)

    def _show_speech(self, line: str) -> None:
        if not self._quiet_moment():
            self._skip_speech()  # things changed while waiting; say nothing
            return
        self.bubble.show_notice(line)
        self.pet.speaking = True
        self.session.add_monologue(line)
        self.speaker.spoke(line)

    def _skip_speech(self) -> None:
        """Give up this turn: start the gap over rather than asking again at once."""
        self.speaker.drop_pending()
        self.speaker.reset_quiet()

    # ---- chat -----------------------------------------------------------------

    def _stop_speaking(self) -> None:
        """The user turns to the pet: drop any spontaneous line, waiting or shown."""
        self._abandon_speech()
        if self.pet.speaking:
            self.bubble.start()
            self.pet.speaking = False
        self.pet.mood.on_interact()
        self.speaker.reset_quiet()

    @Slot()
    def open_input(self) -> None:
        self.pet.touch()
        self._stop_speaking()
        self.input.open_at(self.window.geometry())

    @Slot(str)
    def submit(self, text: str) -> None:
        if self._phase in (WAITING, STREAMING):
            return
        payload = self.session.begin(text)
        if payload is None:
            return
        self._stop_speaking()
        self.bubble.start()
        self.pet.begin_think()
        self._request(payload)

    def _request(self, payload: dict) -> None:
        self._phase = WAITING
        self.worker = self._worker_factory(self.cfg.ollama_url, payload, self.cfg.model)
        self.worker.delta.connect(self._on_delta)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()
        self._wait_timer.start(self.wait_notice_ms)

    @Slot()
    def _on_slow(self) -> None:
        if self._phase == WAITING:
            self.bubble.show_notice(MSG_WAITING)

    @Slot(str)
    def _on_delta(self, text: str) -> None:
        if self._phase == WAITING:
            self._phase = STREAMING
            self._wait_timer.stop()
            self.pet.begin_talk()
            self.bubble.start()
        if self._phase == STREAMING:
            self.bubble.append(text)

    @Slot(str)
    def _on_done(self, reply: str) -> None:
        self._wait_timer.stop()
        self.session.succeed(reply)
        self.pet.mood.on_chat_done()
        if self._phase == WAITING:
            self.bubble.show_notice(MSG_NO_REPLY)
        else:
            self.bubble.finish()
        self._phase = SHOWING

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._wait_timer.stop()
        self._phase = IDLE
        self.pet.end_chat()
        self.session.fail()
        self.bubble.show_notice(message)

    @Slot()
    def _on_bubble_closed(self) -> None:
        self.pet.speaking = False
        if self._phase == SHOWING:
            self._phase = IDLE
            self.pet.end_chat()

    def shutdown(self) -> None:
        self._wait_timer.stop()
        self._abandon_speech()
        self._poll_timer.stop()
        self.window.timer.stop()
        for worker in (self.worker, self.speech_worker):
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
                worker.wait(2000)
        if self._tray is not None:
            self._tray.hide()
        if self.dev_panel is not None:
            self.dev_panel.timer.stop()
            self.dev_panel.close()
        for widget in (self.menu, self.input, self.bubble, self.window):
            widget.hide()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    try:
        cfg = load_config(ROOT / "config.toml")
        actions = load_actions(actions_file(ROOT, cfg.character))
        check_complete(actions)
        sprites = SpriteSet(ROOT / "assets" / cfg.character, cfg.scale)
        personality = load_personality(personality_file(ROOT, cfg.character))
    except (ValueError, OSError, SpriteError) as error:
        QMessageBox.critical(None, "페비", f"시작할 수 없어요.\n\n{error}")
        return 1
    screen = app.primaryScreen()
    rng = random.Random()
    size = (sprites.size.width(), sprites.size.height())
    chooser = Chooser(actions, rng, personality.affinity)
    pet = Pet(actions, chooser, bounds_of(screen), size, rng, cfg.speed)
    window = PetWindow(pet, sprites)
    speaker = Speaker(personality.lines, rng, cfg.monologue_minutes, datetime.now())
    pet_app = PetApp(
        cfg, pet, window, BubbleWindow(), InputWindow(), ChatSession(cfg), speaker=speaker
    )
    pet_app.follow_screen(screen)
    app.primaryScreenChanged.connect(pet_app.follow_screen)
    app.aboutToQuit.connect(pet_app.shutdown)
    window.show()
    pet_app.start_background(QIcon(sprites.pixmap("shime1", False)))
    return app.exec()
