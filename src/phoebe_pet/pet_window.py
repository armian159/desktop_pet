"""The sprite-sized transparent window that shows the pet and takes the mouse."""

from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from .pet import Mode, Pet
from .sprites import SpriteSet

FAST_MS = 16
SLOW_MS = 100
DRAG_THRESHOLD = 4  # px the cursor must travel before a press becomes a drag


class PetWindow(QWidget):
    double_clicked = Signal()
    context_requested = Signal(QPoint)
    moved = Signal(QRect)

    def __init__(self, pet: Pet, sprites: SpriteSet) -> None:
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(sprites.size)
        self._pet = pet
        self._sprites = sprites
        self._pixmap: QPixmap | None = None
        self._press: QPoint | None = None
        self._dragging = False
        self._clock = QElapsedTimer()
        self._clock.start()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.step)
        self.timer.start(FAST_MS)

    def step(self) -> None:
        """Advance the pet by the real time elapsed and redraw what changed."""
        dt = self._clock.restart() / 1000.0
        cursor = QCursor.pos()
        view = self._pet.tick(dt, (cursor.x(), cursor.y()))
        target = QPoint(view.x + view.offset[0], view.y + view.offset[1])
        if target != self.pos():
            self.move(target)
            self.moved.emit(QRect(target, self.size()))
        pixmap = self._sprites.pixmap(view.frame, view.facing_right)
        if pixmap is not self._pixmap:
            self._pixmap = pixmap
            # The mask is what lets clicks on empty pixels reach the window behind.
            self.setMask(pixmap.mask())
            self.update()
        interval = SLOW_MS if view.resting and not self._dragging else FAST_MS
        if self.timer.interval() != interval:
            self.timer.setInterval(interval)

    def paintEvent(self, event) -> None:
        if self._pixmap is not None:
            QPainter(self).drawPixmap(0, 0, self._pixmap)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._press = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event) -> None:
        if self._press is None or self._dragging:
            return
        here = event.globalPosition().toPoint()
        if (here - self._press).manhattanLength() >= DRAG_THRESHOLD:
            self._dragging = True
            self._pet.grab((here.x(), here.y()))
            self.timer.setInterval(FAST_MS)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        self._press = None
        if self._dragging:
            self._dragging = False
            if self._pet.mode is Mode.DRAGGED:
                self._pet.release()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._press = None
            self.double_clicked.emit()

    def contextMenuEvent(self, event) -> None:
        self.context_requested.emit(event.globalPos())
