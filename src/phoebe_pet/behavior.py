"""Action definitions (from actions.toml) and the weighted chooser. No Qt."""

from __future__ import annotations

import random
import tomllib
from dataclasses import dataclass
from pathlib import Path

IDLE_AFTER = 60.0
SURFACES = ("floor", "wall", "ceiling")
# Names the program itself starts, so the table cannot do without them.
REQUIRED = frozenset(
    {"stand", "wall_hold", "ceiling_hold", "fall", "land", "drag", "resist", "think", "talk", "look_at_mouse"}
)
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
    intro: bool = False  # leads into the next action: picks its direction, which that action then keeps


def _frames(name: str, raw: dict) -> tuple[str, ...]:
    frames = tuple(raw.get("frames", ()))
    if not frames or not all(isinstance(f, str) for f in frames):
        raise ValueError(f"actions: '{name}' needs a non-empty frames list")
    if int(raw.get("frame_ms", 0)) <= 0:
        raise ValueError(f"actions: '{name}' needs a positive frame_ms")
    return frames


def check_complete(actions: dict[str, Action]) -> None:
    """Fail early, with the name, if an action the program relies on is absent."""
    missing = sorted(REQUIRED - set(actions))
    if missing:
        raise ValueError(f"actions: required entries are missing: {', '.join(missing)}")


def load_actions(path: Path) -> dict[str, Action]:
    """Read and validate the action table; specials become next-less Actions."""
    with path.open("rb") as f:
        raw = tomllib.load(f)
    try:
        return _build(raw)
    except (TypeError, AttributeError, KeyError) as error:
        # A value of the wrong shape (text for a number, a number for a table...).
        raise ValueError(f"actions: malformed entry ({error})") from error


def _build(raw: dict) -> dict[str, Action]:
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
        if not isinstance(spec["next"], list) or not spec["next"]:
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
            intro=bool(spec.get("intro", False)),
        )
    for action in list(actions.values()):
        for target in action.next:
            if target not in actions:
                raise ValueError(f"actions: '{action.name}' points to unknown action '{target}'")
            if actions[target].surface != action.surface:
                raise ValueError(
                    f"actions: '{action.name}' ({action.surface}) cannot be followed by '{target}' "
                    f"({actions[target].surface}); the program handles moving between surfaces"
                )
    for name, spec in raw.get("special", {}).items():
        if name in actions:
            raise ValueError(f"actions: '{name}' is defined twice")
        actions[name] = Action(name, "floor", _frames(name, spec), int(spec["frame_ms"]), 0.0, (1.0, 1.0), 0.0, 0.0, (), True)
    return actions


class Chooser:
    def __init__(
        self,
        actions: dict[str, Action],
        rng: random.Random,
        affinity: dict[str, dict[str, float]] | None = None,
    ) -> None:
        self._actions = actions
        self._rng = rng
        self._affinity = affinity or {}

    def choose(self, current: str, idle_seconds: float, mood: str = "calm") -> str:
        """Pick what follows `current`, avoiding an immediate repeat if possible; mood scales each weight."""
        options = [n for n in self._actions[current].next if n != current] or list(self._actions[current].next)
        idle = idle_seconds >= IDLE_AFTER
        weights = [
            (self._actions[n].idle_weight if idle else self._actions[n].weight) * self._affinity.get(n, {}).get(mood, 1.0)
            for n in options
        ]
        if not any(weights):
            weights = [1.0] * len(options)
        return self._rng.choices(options, weights)[0]

    def duration(self, name: str) -> float:
        """A time from the action's range, rounded to whole runs of its frames so it ends where it began."""
        action = self._actions[name]
        loop = len(action.frames) * action.frame_ms / 1000
        return max(1, round(self._rng.uniform(*action.duration) / loop)) * loop
