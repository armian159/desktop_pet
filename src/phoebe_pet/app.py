"""Builds the pet and its windows, connects them, and runs the Qt event loop."""

from __future__ import annotations

import random
import sys
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
from .pet import Mode, Pet
from .pet_window import PetWindow
from .physics import Bounds
from .sprites import SpriteSet

ROOT = Path(__file__).resolve().parents[2]
MSG_WAITING = "잠깐만요, 생각을 정리하고 있어요..."
MSG_NO_REPLY = "음... 뭐라고 해야 할지 모르겠어요."
MONOLOGUE_PROMPT = "(방랑자님이 한동안 말이 없다. 페비가 혼잣말처럼 한 문장만 가볍게 말을 건다.)"
MONOLOGUE_GAP = (15 * 60, 40 * 60)  # s of quiet before speaking up, picked anew each time
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
        self.monologue_after = random.uniform(*MONOLOGUE_GAP)
        self._worker_factory = worker_factory
        self._phase = IDLE
        self._monologue = False
        self._quiet = 0.0
        self._last_idle: float | None = None
        self._user_hidden = False
        self._fullscreen_hidden = False
        self._tray: QSystemTrayIcon | None = None
        self._screen: QScreen | None = None
        self.dev_panel: DevPanel | None = None
        self._wait_timer = QTimer(self)
        self._wait_timer.setSingleShot(True)
        self._wait_timer.timeout.connect(self._on_slow)
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
        self.idle_tick(POLL_MS / 1000)

    # ---- speaking up on its own ------------------------------------------------

    def idle_tick(self, seconds: float) -> None:
        """Count quiet time; any interaction with the pet starts the count over."""
        idle = self.pet.idle_seconds
        if self._last_idle is not None and idle < self._last_idle:
            self._quiet = 0.0
        self._last_idle = idle
        self._quiet += seconds
        if not self.cfg.monologue or self._quiet < self.monologue_after:
            return
        if self._phase != IDLE or self.session.busy or not self.window.isVisible():
            return
        if self.pet.mode not in (Mode.AUTO, Mode.PAUSED):
            return
        self._quiet = 0.0
        self.monologue_after = random.uniform(*MONOLOGUE_GAP)
        self._monologue = True
        self.bubble.start()
        self._request(self.session.payload([{"role": "user", "content": MONOLOGUE_PROMPT}]))

    # ---- chat -----------------------------------------------------------------

    @Slot()
    def open_input(self) -> None:
        self.pet.touch()
        self.input.open_at(self.window.geometry())

    @Slot(str)
    def submit(self, text: str) -> None:
        if self._phase in (WAITING, STREAMING):
            return
        payload = self.session.begin(text)
        if payload is None:
            return
        self._monologue = False
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
        if not self._monologue:
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
        if self._monologue:
            self.session.add_assistant(reply)
        else:
            self.session.succeed(reply)
        if self._phase == WAITING:
            if self._monologue:
                self._phase = IDLE
                return
            self.bubble.show_notice(MSG_NO_REPLY)
        else:
            self.bubble.finish()
        self._phase = SHOWING

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._wait_timer.stop()
        self._phase = IDLE
        self.pet.end_chat()
        if self._monologue:
            return  # nobody asked; fail quietly
        self.session.fail()
        self.bubble.show_notice(message)

    @Slot()
    def _on_bubble_closed(self) -> None:
        if self._phase == SHOWING:
            self._phase = IDLE
            self.pet.end_chat()

    def shutdown(self) -> None:
        self._wait_timer.stop()
        self._poll_timer.stop()
        self.window.timer.stop()
        if self.worker is not None and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(2000)
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
    except (ValueError, OSError, SpriteError) as error:
        QMessageBox.critical(None, "페비", f"시작할 수 없어요.\n\n{error}")
        return 1
    screen = app.primaryScreen()
    rng = random.Random()
    size = (sprites.size.width(), sprites.size.height())
    pet = Pet(actions, Chooser(actions, rng), bounds_of(screen), size, rng, cfg.speed)
    window = PetWindow(pet, sprites)
    pet_app = PetApp(cfg, pet, window, BubbleWindow(), InputWindow(), ChatSession(cfg))
    pet_app.follow_screen(screen)
    app.primaryScreenChanged.connect(pet_app.follow_screen)
    app.aboutToQuit.connect(pet_app.shutdown)
    window.show()
    pet_app.start_background(QIcon(sprites.pixmap("shime1", False)))
    return app.exec()
