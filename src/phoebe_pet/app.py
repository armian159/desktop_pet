"""Builds the pet and its windows, connects them, and runs the Qt event loop."""

from __future__ import annotations

import math
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
from .mood import NAMES as MOODS
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
# Seconds a line with a gesture may wait for the pet to stand before it is dropped (mood lines wait on).
WAIT_LIMIT = {"thrown": 60.0, "released": 60.0, "lunch": 600.0, "evening": 600.0, "late_night": 600.0}

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
        gestures: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        names = set(pet.action_names())
        self._gestures = {key: name for key, name in (gestures or {}).items() if name in names}
        self._wait_key: str | None = None  # a line with a gesture waiting for the pet to stand
        self._waited = 0.0
        self._panel_wait = False  # the waiting line came from the developer panel's button
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
        self._user_talked = clock()  # when the user last talked to the pet
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
            self.dev_panel = DevPanel(
                self.pet,
                speak_now=self._speak_from_panel,
                next_speech=lambda: self.speaker.seconds_until_due(self.pet.mood.name),
                waiting=lambda: self.waiting_key,
            )
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
        if not visible and self.pet.speaking:
            # A monologue is not worth bringing back later; drop it.
            self.bubble.start()
            self.pet.speaking = False
            self._release_hold()
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
        if self.window.isVisible():
            pet.mood.tick(seconds, pet.action, now, pet.mouse_near)
        else:
            # Out of sight the pet is frozen; count it as awake with nobody around.
            pet.mood.tick(seconds, "stand", now, False)
        clock = self._clock()
        events = pet.take_events()
        slot = speaker.clock_event(now)
        if slot is not None:
            events.append(slot)
        for event in events:
            speaker.note_event(event, clock)
        speaker.tick(seconds, pet.mood.name)
        if self._speech_live is not None:
            return  # a line is on its way; its event must stay pending for spoke()
        if self._panel_wait:
            self._tick_panel_wait()
            return
        key = speaker.due()
        if self._wait_key in MOODS and key in MOODS:
            key = self._wait_key  # a mood line keeps the mood it started waiting with
        # A line already waiting rides out a fall (she let go of a wall); anything else drops it.
        if key is not None and not self.can_speak(airborne=key == self._wait_key):
            speaker.drop_pending()  # an event line said later would be stale
            key = None
        if key is None:
            self._wait_key = None
            pet.hold_stand = pet.hold_stand and pet.speaking  # kept only while a gesture line shows
            return
        if key in self._gestures and not pet.standing:
            self._wait(key, seconds)
        else:
            self.speak(key)

    @property
    def waiting_key(self) -> str | None:
        return self._wait_key

    def _wait(self, key: str, seconds: float) -> None:
        """Hold a line with a gesture until the pet stands; event and clock lines only so long."""
        if key == self._wait_key:
            self._waited += seconds
        else:
            self._wait_key, self._waited = key, 0.0
        self.pet.hold_stand = True
        if self._waited > WAIT_LIMIT.get(key, math.inf):
            self.speaker.drop_pending()
            self._release_hold()

    def _release_hold(self) -> None:
        self._wait_key = None
        self._panel_wait = False
        self.pet.hold_stand = False

    def can_speak(self, airborne: bool = False) -> bool:
        return self.cfg.monologue and self._free_to_speak(airborne)

    def _free_to_speak(self, airborne: bool = False) -> bool:
        return self._speech_live is None and self._quiet_moment(airborne)

    def _speak_from_panel(self) -> None:
        """The developer panel's button: speak even with monologues off, but never at a bad moment.

        A line with a gesture waits for the pet to stand, like an automatic one.
        """
        if not self._free_to_speak():
            return
        key = self.pet.mood.name
        if key in self._gestures and not self.pet.standing:
            self._wait_key, self._panel_wait = key, True
            self.pet.hold_stand = True
        else:
            self.speak(key)

    def _tick_panel_wait(self) -> None:
        """The panel's line waits for standing on its own, whether monologues are on or not."""
        if not self._free_to_speak(airborne=True):
            self._release_hold()  # dragged, hidden or talked to: forget it
        elif self.pet.standing:
            self.speak(self._wait_key)

    def _quiet_moment(self, airborne: bool = False) -> bool:
        """Nothing is going on that a spontaneous line would get in the way of.

        `airborne`: falling or landing (not dragged) also counts, for a line already waiting.
        """
        mode = self.pet.mode
        return (
            self._phase == IDLE
            and not self.session.busy
            and self.window.isVisible()
            and not self.input.isVisible()
            and not self.bubble.isVisible()
            and (mode is Mode.AUTO or (airborne and mode is Mode.AIR))
        )

    def speak(self, key: str) -> None:
        """Ask the model for one line about `key`; a stock line if it is slow or fails."""
        self._abandon_speech()
        self._speech_key = key
        self._wait_key = None
        self._panel_wait = False
        self.pet.hold_stand = key in self._gestures  # stay standing while the line is on its way
        if self.speech_worker is not None and self.speech_worker.isRunning():
            # An abandoned request cannot be cut short; never stack another on top.
            self._speak_fallback()
            return
        pet = self.pet
        situation = self.speaker.situation(
            key, pet.mood.name, pet.action, self._now(), self._clock() - self._user_talked
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
        if self._speech_live is not None and self.speech_worker is not None:
            self.speech_worker.requestInterruption()  # cooperative; never waited on
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
        gesture = self._gestures.get(self._speech_key)
        if gesture is not None and self.pet.last_action != gesture:
            # Only if standing; otherwise just the words. Never the same gesture twice in a row.
            self.pet.play(gesture)
        self.pet.speaking = True
        self.session.add_monologue(line)
        self.speaker.spoke(line)

    def _skip_speech(self) -> None:
        """Give up this turn: start the gap over rather than asking again at once."""
        self.speaker.drop_pending()
        self.speaker.reset_quiet()
        self._release_hold()

    # ---- chat -----------------------------------------------------------------

    def _stop_speaking(self) -> None:
        """The user turns to the pet: drop any spontaneous line, waiting or shown."""
        self._abandon_speech()
        if self.pet.speaking:
            self.bubble.start()
            self.pet.speaking = False
        self._release_hold()
        self.pet.mood.on_interact()
        self.speaker.reset_quiet()
        self._user_talked = self._clock()

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
        self._user_talked = self._clock()
        if self._phase == WAITING:
            self.bubble.show_notice(MSG_NO_REPLY)
        else:
            self.bubble.finish()
        self._phase = SHOWING

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._wait_timer.stop()
        self._phase = IDLE
        self._user_talked = self._clock()
        self.pet.end_chat()
        self.session.fail()
        self.bubble.show_notice(message)

    @Slot()
    def _on_bubble_closed(self) -> None:
        self.pet.speaking = False
        self._release_hold()
        if self._phase == SHOWING:
            self._phase = IDLE
            self.pet.end_chat()
            self.speaker.reset_quiet()  # the gap runs from when the user is done reading

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
        cfg, pet, window, BubbleWindow(), InputWindow(), ChatSession(cfg), speaker=speaker,
        gestures=personality.gestures,
    )
    pet_app.follow_screen(screen)
    app.primaryScreenChanged.connect(pet_app.follow_screen)
    app.aboutToQuit.connect(pet_app.shutdown)
    window.show()
    pet_app.start_background(QIcon(sprites.pixmap("shime1", False)))
    return app.exec()
