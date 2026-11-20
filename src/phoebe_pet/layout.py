"""Where bubbles go and how long they stay. Geometry only, no widgets."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize

LONG_CHARS = 200
LONG_LINES = 6


def is_long(text: str) -> bool:
    """Replies that need the scrolling bubble: long, many lines, or code."""
    return len(text) > LONG_CHARS or text.count("\n") > LONG_LINES or "```" in text


def hide_delay_ms(text: str) -> int:
    return max(4000, min(3000 + 60 * len(text), 30000))


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, max(low, high)))


def place(anchor: QRect, size: QSize, bounds: QRect, gap: int = 8) -> QPoint:
    """Centre a bubble above the pet, or below it when there is no room."""
    x = anchor.x() + anchor.width() // 2 - size.width() // 2
    y = anchor.y() - size.height() - gap
    if y < bounds.y():
        y = anchor.y() + anchor.height() + gap
    return QPoint(
        _clamp(x, bounds.x(), bounds.x() + bounds.width() - size.width()),
        _clamp(y, bounds.y(), bounds.y() + bounds.height() - size.height()),
    )


def place_beside(anchor: QRect, size: QSize, bounds: QRect, gap: int = 8) -> QPoint:
    """Put a box to the right of the pet, or to the left at the screen edge."""
    right_edge = bounds.x() + bounds.width()
    x = anchor.x() + anchor.width() + gap
    if x + size.width() > right_edge:
        x = anchor.x() - size.width() - gap
    y = anchor.y() + (anchor.height() - size.height()) // 2
    return QPoint(
        _clamp(x, bounds.x(), right_edge - size.width()),
        _clamp(y, bounds.y(), bounds.y() + bounds.height() - size.height()),
    )
