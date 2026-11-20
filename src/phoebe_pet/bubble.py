"""The speech bubble above the pet and the box you type into."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from .layout import hide_delay_ms, is_long, place, place_beside

TAIL = 10
FONT = QFont("Malgun Gothic", 10)
MONO = QFont("Consolas", 10)
FILL = QColor("#ffffff")
EDGE = QColor("#39456b")
INPUT_HINT = "Enter로 보내기 · Esc로 닫기"


def _screen() -> QRect:
    return QGuiApplication.primaryScreen().availableGeometry()


class BubbleWindow(QWidget):
    """Shows the reply. Never takes focus; short text hides itself, long text scrolls."""

    closed = Signal()

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._text = ""
        self._suppressed = False
        self._finished = False
        self._dismissed = False  # the current text was closed or timed out
        self._delay_ms: int | None = None
        self._anchor = QRect(0, 0, 1, 1)
        self._below = False
        self._label = QLabel()
        self._label.setFont(FONT)
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(292)
        self._label.setStyleSheet("color: #232a44;")
        self._label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._scroll = QPlainTextEdit()
        self._scroll.setReadOnly(True)
        self._scroll.setFont(MONO)
        self._scroll.setFixedSize(452, 300)
        self._scroll.setFocusPolicy(Qt.NoFocus)
        self._scroll.setStyleSheet("QPlainTextEdit { border: none; background: transparent; color: #232a44; }")
        self.copy_button = QPushButton("복사")
        self.close_button = QPushButton("닫기")
        for button in (self.copy_button, self.close_button):
            button.setFont(FONT)
            button.setFocusPolicy(Qt.NoFocus)
        self.copy_button.clicked.connect(self._copy)
        self.close_button.clicked.connect(self._dismiss)
        self._buttons = QWidget()
        row = QHBoxLayout(self._buttons)
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        row.addWidget(self.copy_button)
        row.addWidget(self.close_button)
        box = QVBoxLayout(self)
        box.setContentsMargins(14, 10 + TAIL, 14, 10 + TAIL)
        box.addWidget(self._label)
        box.addWidget(self._scroll)
        box.addWidget(self._buttons)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._dismiss)
        self._set_scroll_mode(False)

    def text(self) -> str:
        return self._text

    def is_scroll_mode(self) -> bool:
        return self._scroll_mode

    def start(self) -> None:
        """Empty the bubble for a new message; it appears with the first text."""
        self._timer.stop()
        self._text = ""
        self._finished = False
        self._dismissed = False
        self._set_scroll_mode(False)
        self._label.setText("")
        self.hide()

    def suppress(self, on: bool) -> None:
        """While suppressed the bubble keeps collecting text but stays off screen."""
        if on == self._suppressed:
            return
        self._suppressed = on
        if on:
            self._timer.stop()
            self.hide()
        elif self._text and not self._dismissed:
            self._present()
            if self._finished:
                self._arm()

    def _present(self) -> None:
        if self._suppressed:
            return
        self.adjustSize()
        self._reposition()
        self.show()

    def _arm(self) -> None:
        if not self._scroll_mode and not self._suppressed:
            self._timer.start(hide_delay_ms(self._text) if self._delay_ms is None else self._delay_ms)

    def append(self, delta: str) -> None:
        self._timer.stop()
        self._finished = False
        self._text += delta
        if is_long(self._text):
            self._set_scroll_mode(True)
            self._scroll.setPlainText(self._text)
            bar = self._scroll.verticalScrollBar()
            bar.setValue(bar.maximum())
        else:
            self._label.setText(self._text)
        self._present()

    def finish(self, delay_ms: int | None = None) -> None:
        """The message is complete: short ones go away on their own."""
        self._finished = True
        self._delay_ms = delay_ms
        self._arm()

    def show_notice(self, text: str) -> None:
        self.start()
        self._label.setText(text)
        self._text = text
        self._present()
        self.finish()

    def follow(self, pet_rect: QRect) -> None:
        self._anchor = QRect(pet_rect)
        if self.isVisible():
            self._reposition()

    def _set_scroll_mode(self, on: bool) -> None:
        self._scroll_mode = on
        self._label.setVisible(not on)
        self._scroll.setVisible(on)
        self._buttons.setVisible(on)

    def _reposition(self) -> None:
        spot = place(self._anchor, self.size(), _screen())
        below = spot.y() > self._anchor.y()
        if below != self._below:
            self._below = below
            self.update()
        self.move(spot)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._text)

    def _dismiss(self) -> None:
        self._timer.stop()
        self._dismissed = True
        if self.isVisible():
            self.hide()
            self.closed.emit()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and not self._scroll_mode:
            self._copy()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        body = QRectF(self.rect()).adjusted(1, TAIL, -1, -TAIL)
        path = QPainterPath()
        path.addRoundedRect(body, 12, 12)
        # The tail points at the pet, wherever the bubble ended up.
        tip_x = self._anchor.center().x() - self.x()
        tip_x = max(body.left() + 20, min(tip_x, body.right() - 20))
        edge_y, tip_y = (body.top(), 1.0) if self._below else (body.bottom(), self.height() - 1.0)
        tail = QPainterPath()
        tail.addPolygon(QPolygonF([QPointF(tip_x - 8, edge_y), QPointF(tip_x + 8, edge_y), QPointF(tip_x, tip_y)]))
        painter.setPen(QPen(EDGE, 2))
        painter.setBrush(FILL)
        painter.drawPath(path.united(tail))


class InputWindow(QWidget):
    """A small box beside the pet. The only window here that takes the keyboard."""

    submitted = Signal(str)

    def __init__(self) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setFixedSize(280, 68)
        self.edit = QPlainTextEdit()
        self.edit.setFont(FONT)
        self.edit.setPlaceholderText(INPUT_HINT)
        self.edit.setStyleSheet(
            "QPlainTextEdit { border: 2px solid #39456b; border-radius: 8px; padding: 4px;"
            " background: #ffffff; color: #232a44; }"
        )
        self.edit.installEventFilter(self)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(self.edit)

    def open_at(self, pet_rect: QRect) -> None:
        self.move(place_beside(pet_rect, self.size(), _screen()))
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.edit and event.type() == QEvent.KeyPress:
            key = event.key()
            if key == Qt.Key_Escape:
                self.hide()
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers() & Qt.ShiftModifier:
                text = self.edit.toPlainText().strip()
                if text:
                    self.edit.clear()
                    self.hide()
                    self.submitted.emit(text)
                return True
        return super().eventFilter(watched, event)
