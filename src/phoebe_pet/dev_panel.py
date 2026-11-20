"""A small window for trying actions out without waiting for the pet to pick them."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QCheckBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .mood import NAMES
from .pet import Mode, Pet

COLUMNS = 3
REFRESH_MS = 200


class DevPanel(QWidget):
    def __init__(
        self,
        pet: Pet,
        speak_now: Callable[[], None] | None = None,
        next_speech: Callable[[], float | None] | None = None,
    ) -> None:
        super().__init__(None, Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("페비 개발자 패널")
        self._pet = pet
        self._chosen: str | None = None
        self._speak_now = speak_now
        self._next_speech = next_speech
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
        self.speak_button = QPushButton("지금 말하기")
        self.speak_button.setEnabled(speak_now is not None)
        self.speak_button.clicked.connect(self._speak)
        self.mood_button = QPushButton("기분 바꾸기")
        self.mood_button.setToolTip("기분을 하나씩 돌아가며 고정합니다. 한 바퀴 돌면 원래대로 돌아갑니다.")
        self.mood_button.clicked.connect(self.cycle_mood)
        box = QVBoxLayout(self)
        box.addWidget(self.status)
        box.addLayout(grid)
        box.addWidget(self.repeat)
        row = QHBoxLayout()
        row.addWidget(self.speak_button)
        row.addWidget(self.mood_button)
        box.addLayout(row)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(REFRESH_MS)
        self.refresh()

    def pick(self, name: str) -> None:
        self._chosen = name
        self._pet.force(name)
        self.refresh()

    def _speak(self) -> None:
        if self._speak_now is not None:
            self._speak_now()
        self.refresh()

    def cycle_mood(self) -> None:
        """Force each mood in turn; after the last one the pet's own mood takes over again."""
        mood = self._pet.mood
        index = NAMES.index(mood.forced) + 1 if mood.forced else 0
        mood.forced = NAMES[index] if index < len(NAMES) else None
        self.refresh()

    def _next_speech_text(self) -> str:
        seconds = self._next_speech() if self._next_speech is not None else None
        if seconds is None:
            return "다음 혼잣말 —"
        minutes, rest = divmod(int(seconds), 60)
        return f"다음 혼잣말 {minutes}분 {rest}초"

    def refresh(self) -> None:
        pet = self._pet
        # While it is being dragged, or still falling and landing, leave it be.
        busy = pet.mode in (Mode.DRAGGED, Mode.AIR)
        if self.repeat.isChecked() and self._chosen and not busy and pet.action != self._chosen:
            pet.force(self._chosen)
        mood = pet.mood
        self.status.setText(
            f"상태: {pet.mode.value}   동작: {pet.action}   가만히 둔 시간: {pet.idle_seconds:.0f}초\n"
            f"기운 {mood.energy:.2f}  심심함 {mood.boredom:.2f}  기분 {mood.cheer:.2f}  [{mood.name}]  "
            f"{self._next_speech_text()}"
        )
