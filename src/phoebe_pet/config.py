"""User settings loaded from config.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class Config:
    character: str = "placeholder"
    scale: float = 1.0
    model: str = "phoebe"
    ollama_url: str = "http://localhost:11434"
    speed: float = 1.0
    monologue: bool = False
    history_turns: int = 12
    keep_alive: str = "30m"


_RANGES = {"scale": (0.25, 4.0), "speed": (0.25, 4.0)}


def _coerce(key: str, value: object, default: object) -> object:
    if isinstance(default, bool):
        ok = isinstance(value, bool)
    elif isinstance(default, float):
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        value = float(value) if ok else value
    elif isinstance(default, int):
        ok = isinstance(value, int) and not isinstance(value, bool)
    else:
        ok = isinstance(value, str)
    if not ok:
        raise ValueError(f"config: '{key}' has the wrong type: {value!r}")
    return value


def load_config(path: Path) -> Config:
    """Read settings; a missing file gives defaults, unknown keys are ignored."""
    if not path.is_file():
        return Config()
    with path.open("rb") as f:
        raw = tomllib.load(f)
    defaults = Config()
    values: dict[str, object] = {}
    for field in fields(Config):
        if field.name in raw:
            values[field.name] = _coerce(field.name, raw[field.name], getattr(defaults, field.name))
    for key, (low, high) in _RANGES.items():
        if key in values and not low <= values[key] <= high:
            raise ValueError(f"config: '{key}' must be between {low} and {high}")
    if values.get("history_turns", 1) < 1:
        raise ValueError("config: 'history_turns' must be at least 1")
    return Config(**values)
