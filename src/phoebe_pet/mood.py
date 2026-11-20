"""Slow-moving mood state (energy, boredom, cheer) and the name derived from it. No Qt."""

from __future__ import annotations

from datetime import datetime

NAMES = ("sleepy", "sulky", "bored", "happy", "calm")
SLEEP_ACTIONS = frozenset({"lie", "doze_off"})
RUN_ACTIONS = frozenset({"run"})

_MARGIN = 0.05
_REST_CHEER = 0.6
# name -> (value attribute, True when low values trigger, threshold), in priority order.
_RULES = (
    ("sleepy", "energy", True, 0.3),
    ("sulky", "cheer", True, 0.3),
    ("bored", "boredom", False, 0.7),
    ("happy", "cheer", False, 0.8),
)


def _is_night(now: datetime) -> bool:
    return now.hour >= 23 or now.hour < 6


def _start_energy(now: datetime) -> float:
    h = now.hour
    if 6 <= h < 11:
        return 0.8
    if 11 <= h < 18:
        return 0.6
    if 18 <= h < 23:
        return 0.45
    return 0.3


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


class Mood:
    def __init__(self, now: datetime) -> None:
        self.energy = _start_energy(now)
        self.boredom = 0.2
        self.cheer = _REST_CHEER
        self.forced: str | None = None
        self._held = "calm"

    def tick(self, seconds: float, action: str, now: datetime, mouse_near: bool) -> None:
        hours = seconds / 3600.0
        if action in SLEEP_ACTIONS:
            self.energy += 0.6 * hours
        else:
            drain = 0.15
            if _is_night(now):
                drain *= 2
            if action in RUN_ACTIONS:
                drain *= 2
            self.energy -= drain * hours
        self.energy = _clamp(self.energy)
        self.boredom = _clamp(self.boredom + (-0.5 if mouse_near else 0.5) * hours)
        step = 0.2 * hours
        if self.cheer < _REST_CHEER:
            self.cheer = min(_REST_CHEER, self.cheer + step)
        else:
            self.cheer = max(_REST_CHEER, self.cheer - step)

    def on_interact(self) -> None:
        self.boredom = _clamp(self.boredom - 0.3)

    def on_chat_done(self) -> None:
        self.boredom = _clamp(self.boredom - 0.5)
        self.cheer = _clamp(self.cheer + 0.15)

    def on_throw(self) -> None:
        """Thrown hard; the pet decides what counts as hard."""
        self.cheer = _clamp(self.cheer - 0.25)

    def on_resist(self) -> None:
        """Released after struggling in the user's grip."""
        self.cheer = _clamp(self.cheer - 0.1)

    @property
    def name(self) -> str:
        if self.forced:
            return self.forced
        for name, attr, low, limit in _RULES:
            margin = _MARGIN if name == self._held else 0.0
            value = getattr(self, attr)
            if (value < limit + margin) if low else (value > limit - margin):
                self._held = name
                return name
        self._held = "calm"
        return "calm"
