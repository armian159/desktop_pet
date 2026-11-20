"""Loads a Shimeji-style image folder into ready-to-draw pixmaps."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap

from .frames import SpriteError, resolve


class SpriteSet:
    def __init__(self, folder: Path, scale: float) -> None:
        self._images: dict[str, QImage] = {}
        if folder.is_dir():
            for path in folder.glob("*.png"):
                image = QImage(str(path))
                if not image.isNull():
                    self._images[path.stem.lower()] = image
        if "shime1" not in self._images:
            raise SpriteError(f"shime1.png not found in {folder}")
        base = self._images["shime1"]
        self.size = QSize(max(1, round(base.width() * scale)), max(1, round(base.height() * scale)))
        self._available = set(self._images)
        self._cache: dict[tuple[str, bool], QPixmap] = {}

    def pixmap(self, name: str, facing_right: bool) -> QPixmap:
        """Frame `name` at the set's size; art faces left unless mirrored."""
        key = (resolve(name, self._available), facing_right)
        cached = self._cache.get(key)
        if cached is None:
            cached = self._cache[key] = self._render(*key)
        return cached

    def _render(self, name: str, facing_right: bool) -> QPixmap:
        image = self._images[name].scaled(self.size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        canvas = QImage(self.size, QImage.Format_ARGB32_Premultiplied)
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        # Odd-sized frames sit bottom-centre, where the feet are.
        painter.drawImage((self.size.width() - image.width()) // 2, self.size.height() - image.height(), image)
        painter.end()
        if facing_right:
            canvas = canvas.flipped(Qt.Horizontal)
        return QPixmap.fromImage(canvas)
