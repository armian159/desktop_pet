"""Per-mood action affinities and fallback speech lines from personality.toml. No Qt."""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from phoebe_pet.mood import NAMES

LINE_KEYS = NAMES + ("thrown", "woke", "released", "lunch", "evening", "late_night")


@dataclass(frozen=True)
class Personality:
    affinity: dict[str, dict[str, float]]
    lines: dict[str, tuple[str, ...]]
    gestures: dict[str, str] = field(default_factory=dict)


def personality_file(root: Path, character: str) -> Path:
    """A character folder may carry its own personality.toml."""
    own = root / "assets" / character / "personality.toml"
    return own if own.is_file() else root / "personality.toml"


def load_personality(path: Path) -> Personality:
    """Read and validate the file; a missing file means no personality at all."""
    if not path.is_file():
        return Personality({}, {})
    with path.open("rb") as f:
        raw = tomllib.load(f)
    try:
        return Personality(
            _affinity(raw.get("affinity", {})),
            _lines(raw.get("lines", {})),
            _gestures(raw.get("gestures", {})),
        )
    except (TypeError, AttributeError) as error:
        raise ValueError(f"personality: malformed entry ({error})") from error


def _affinity(table: dict) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for action, factors in table.items():
        result[action] = {}
        for mood, factor in factors.items():
            if mood not in NAMES:
                raise ValueError(f"personality: '{action}' has unknown mood '{mood}'")
            if isinstance(factor, bool) or not isinstance(factor, (int, float)):
                raise ValueError(f"personality: '{action}' factor '{mood}' is not a number")
            if not math.isfinite(factor):
                raise ValueError(f"personality: '{action}' factor '{mood}' is not finite")
            if factor < 0:
                raise ValueError(f"personality: '{action}' has a negative factor for '{mood}'")
            result[action][mood] = float(factor)
    return result


def _lines(table: dict) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for key, items in table.items():
        if not isinstance(items, list) or not all(isinstance(s, str) for s in items):
            raise ValueError(f"personality: lines '{key}' must be a list of text")
        result[key] = tuple(items)
    return result


def _gestures(table: dict) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, action in table.items():
        if key not in LINE_KEYS:
            raise ValueError(f"personality: gestures has unknown key '{key}'")
        if not isinstance(action, str):
            raise ValueError(f"personality: gestures '{key}' must be text")
        result[key] = action
    return result
