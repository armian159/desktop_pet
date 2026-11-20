"""Action definitions (from actions.toml) and the weighted chooser. No Qt."""

from __future__ import annotations

import random
import tomllib
from dataclasses import dataclass
from pathlib import Path

IDLE_AFTER = 60.0
SURFACES = ("floor", "wall", "ceiling")
_REQUIRED = ("surface", "frames", "frame_ms", "speed", "duration", "weight", "idle_weight", "next")


@dataclass(frozen=True)
class Action:
    name: str
    surface: str
    frames: tuple[str, ...]
    frame_ms: int
    speed: float
    duration: tuple[float, float]
    weight: float
    idle_weight: float
    next: tuple[str, ...]
    resting: bool
    offset: tuple[int, int] = (0, 0)


def _frames(name: str, raw: dict) -> tuple[str, ...]:
    frames = tuple(raw.get("frames", ()))
    if not frames or not all(isinstance(f, str) for f in frames):
        raise ValueError(f"actions: '{name}' needs a non-empty frames list")
    if int(raw.get("frame_ms", 0)) <= 0:
        raise ValueError(f"actions: '{name}' needs a positive frame_ms")
    return frames


def load_actions(path: Path) -> dict[str, Action]:
    """Read and validate the action table; specials become next-less Actions."""
    with path.open("rb") as f:
        raw = tomllib.load(f)
    actions: dict[str, Action] = {}
    for name, spec in raw.get("action", {}).items():
        for key in _REQUIRED:
            if key not in spec:
                raise ValueError(f"actions: '{name}' is missing '{key}'")
        if spec["surface"] not in SURFACES:
            raise ValueError(f"actions: '{name}' has unknown surface '{spec['surface']}'")
        low, high = (float(v) for v in spec["duration"])
        if not 0 < low <= high:
            raise ValueError(f"actions: '{name}' has a bad duration range")
        if not spec["next"]:
            raise ValueError(f"actions: '{name}' needs at least one next action")
        if spec["weight"] < 0 or spec["idle_weight"] < 0:
            raise ValueError(f"actions: '{name}' has a negative weight")
        dx, dy = spec.get("offset", (0, 0))
        actions[name] = Action(
            name=name,
            surface=spec["surface"],
            frames=_frames(name, spec),
            frame_ms=int(spec["frame_ms"]),
            speed=float(spec["speed"]),
            duration=(low, high),
            weight=float(spec["weight"]),
            idle_weight=float(spec["idle_weight"]),
            next=tuple(spec["next"]),
            resting=float(spec["speed"]) == 0,
            offset=(int(dx), int(dy)),
        )
    for action in list(actions.values()):
        for target in action.next:
            if target not in actions:
                raise ValueError(f"actions: '{action.name}' points to unknown action '{target}'")
    for name, spec in raw.get("special", {}).items():
        if name in actions:
            raise ValueError(f"actions: '{name}' is defined twice")
        actions[name] = Action(name, "floor", _frames(name, spec), int(spec["frame_ms"]), 0.0, (1.0, 1.0), 0.0, 0.0, (), True)
    return actions


class Chooser:
    def __init__(self, actions: dict[str, Action], rng: random.Random) -> None:
        self._actions = actions
        self._rng = rng

    def choose(self, current: str, idle_seconds: float) -> str:
        """Pick what follows `current`, avoiding an immediate repeat if possible."""
        options = [n for n in self._actions[current].next if n != current] or list(self._actions[current].next)
        idle = idle_seconds >= IDLE_AFTER
        weights = [self._actions[n].idle_weight if idle else self._actions[n].weight for n in options]
        if not any(weights):
            weights = [1.0] * len(options)
        return self._rng.choices(options, weights)[0]

    def duration(self, name: str) -> float:
        return self._rng.uniform(*self._actions[name].duration)
