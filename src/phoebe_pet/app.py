"""Builds the pet and its windows and runs the Qt event loop."""

from __future__ import annotations

import random
import sys
from pathlib import Path

from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QApplication, QMessageBox

from .behavior import Chooser, load_actions
from .config import load_config
from .frames import SpriteError
from .pet import Pet
from .pet_window import PetWindow
from .physics import Bounds
from .sprites import SpriteSet

ROOT = Path(__file__).resolve().parents[2]


def bounds_of(screen: QScreen) -> Bounds:
    g = screen.availableGeometry()
    return Bounds(g.left(), g.top(), g.left() + g.width(), g.top() + g.height())


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
    screen.availableGeometryChanged.connect(lambda _rect: pet.set_bounds(bounds_of(screen)))
    window.show()
    return app.exec()
