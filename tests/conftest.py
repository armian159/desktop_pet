import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def pet():
    from phoebe_pet.behavior import Chooser, load_actions
    from phoebe_pet.pet import Pet
    from phoebe_pet.physics import Bounds

    actions = load_actions(ROOT / "actions.toml")
    rng = random.Random(0)
    return Pet(actions, Chooser(actions, rng), Bounds(0, 0, 1920, 1040), (128, 128), rng)


@pytest.fixture
def sprites(qapp):
    from phoebe_pet.sprites import SpriteSet

    return SpriteSet(ROOT / "assets" / "placeholder", 1.0)


@pytest.fixture
def win(qapp, pet, sprites):
    from phoebe_pet.pet_window import PetWindow

    window = PetWindow(pet, sprites)
    window.show()
    window.step()
    yield window
    window.timer.stop()
    window.close()


@pytest.fixture
def gesture_pet():
    """A pet whose action table also has two gestures: stand-alikes that go back to standing."""
    import dataclasses

    from phoebe_pet.behavior import Chooser, load_actions
    from phoebe_pet.pet import Pet
    from phoebe_pet.physics import Bounds

    actions = load_actions(ROOT / "actions.toml")
    for name in ("gesture_sleepy", "gesture_thrown"):
        actions[name] = dataclasses.replace(
            actions["stand"], name=name, next=("stand",), weight=0, idle_weight=0, duration=(0.1, 0.1)
        )
    rng = random.Random(0)
    return Pet(actions, Chooser(actions, rng), Bounds(0, 0, 1920, 1040), (128, 128), rng)
