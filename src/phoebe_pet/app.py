"""Builds the pet and its windows, connects them, and runs the Qt event loop."""

from __future__ import annotations

import random
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Slot
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QApplication, QMessageBox

from .behavior import Chooser, load_actions
from .bubble import BubbleWindow, InputWindow
from .chat import ChatSession, ChatWorker
from .config import Config, load_config
from .frames import SpriteError
from .pet import Pet
from .pet_window import PetWindow
from .physics import Bounds
from .sprites import SpriteSet

ROOT = Path(__file__).resolve().parents[2]
MSG_WAITING = "잠깐만요, 생각을 정리하고 있어요..."
MSG_NO_REPLY = "음... 뭐라고 해야 할지 모르겠어요."

# Where one chat turn stands.
IDLE, WAITING, STREAMING, SHOWING = "idle", "waiting", "streaming", "showing"


def bounds_of(screen: QScreen) -> Bounds:
    g = screen.availableGeometry()
    return Bounds(g.left(), g.top(), g.left() + g.width(), g.top() + g.height())


class PetApp(QObject):
    """Glue between the pet, its windows and the chat session."""

    def __init__(
        self,
        cfg: Config,
        pet: Pet,
        window: PetWindow,
        bubble: BubbleWindow,
        input: InputWindow,
        session: ChatSession,
        worker_factory=ChatWorker,
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
        self._worker_factory = worker_factory
        self._phase = IDLE
        self._wait_timer = QTimer(self)
        self._wait_timer.setSingleShot(True)
        self._wait_timer.timeout.connect(self._on_slow)
        window.double_clicked.connect(self.open_input)
        window.moved.connect(bubble.follow)
        input.submitted.connect(self.submit)
        bubble.closed.connect(self._on_bubble_closed)
        bubble.follow(window.geometry())

    @Slot()
    def open_input(self) -> None:
        self.pet.touch()
        self.input.open_at(self.window.geometry())

    @Slot(str)
    def submit(self, text: str) -> None:
        payload = self.session.begin(text)
        if payload is None:
            return
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
        if self._phase == WAITING:
            self.bubble.show_notice(MSG_NO_REPLY)
        else:
            self.bubble.finish()
        self._phase = SHOWING

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._wait_timer.stop()
        self.session.fail()
        self._phase = IDLE
        self.bubble.show_notice(message)
        self.pet.end_chat()

    @Slot()
    def _on_bubble_closed(self) -> None:
        if self._phase == SHOWING:
            self._phase = IDLE
            self.pet.end_chat()

    def shutdown(self) -> None:
        self._wait_timer.stop()
        self.window.timer.stop()
        if self.worker is not None and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(2000)
        for widget in (self.input, self.bubble, self.window):
            widget.hide()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    try:
        cfg = load_config(ROOT / "config.toml")
        actions = load_actions(ROOT / "actions.toml")
        sprites = SpriteSet(ROOT / "assets" / cfg.character, cfg.scale)
    except (ValueError, OSError, SpriteError) as error:
        QMessageBox.critical(None, "페비", f"시작할 수 없어요.\n\n{error}")
        return 1
    screen = app.primaryScreen()
    rng = random.Random()
    size = (sprites.size.width(), sprites.size.height())
    pet = Pet(actions, Chooser(actions, rng), bounds_of(screen), size, rng, cfg.speed)
    window = PetWindow(pet, sprites)
    pet_app = PetApp(cfg, pet, window, BubbleWindow(), InputWindow(), ChatSession(cfg))
    screen.availableGeometryChanged.connect(lambda _rect: pet.set_bounds(bounds_of(screen)))
    app.aboutToQuit.connect(pet_app.shutdown)
    window.show()
    return app.exec()
