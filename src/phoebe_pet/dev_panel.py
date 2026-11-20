"""A small window for trying actions out without waiting for the pet to pick them."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QCheckBox, QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .pet import Mode, Pet

COLUMNS = 3
REFRESH_MS = 200


class DevPanel(QWidget):
    def __init__(self, pet: Pet) -> None:
        super().__init__(None, Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("페비 개발자 패널")
        self._pet = pet
        self._chosen: str | None = None
        self.status = QLabel()
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.repeat = QCheckBox("고른 동작 반복")
        self.repeat.setToolTip("동작이 끝나도 다시 시작합니다. 끄면 원래대로 알아서 움직입니다.")
        self.buttons: dict[str, QPushButton] = {}
        grid = QGridLayout()
        for index, name in enumerate(pet.action_names()):
            button = QPushButton(name)
            button.clicked.connect(lambda _checked=False, n=name: self.pick(n))
            grid.addWidget(button, index // COLUMNS, index % COLUMNS)
            self.buttons[name] = button
        box = QVBoxLayout(self)
        box.addWidget(self.status)
        box.addLayout(grid)
        box.addWidget(self.repeat)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(REFRESH_MS)
        self.refresh()

    def pick(self, name: str) -> None:
        self._chosen = name
        self._pet.force(name)
        self.refresh()

    def refresh(self) -> None:
        pet = self._pet
        # While it is being dragged, or still falling and landing, leave it be.
        busy = pet.mode in (Mode.DRAGGED, Mode.AIR)
        if self.repeat.isChecked() and self._chosen and not busy and pet.action != self._chosen:
            pet.force(self._chosen)
        self.status.setText(f"상태: {pet.mode.value}   동작: {pet.action}   가만히 둔 시간: {pet.idle_seconds:.0f}초")
