"""Frame-name fallback rules so partial Shimeji image sets still work."""

from __future__ import annotations


class SpriteError(Exception):
    """The character image folder cannot be used."""


def _chain(*nums: int) -> tuple[str, ...]:
    return tuple(f"shime{n}" for n in nums)


# name -> candidates tried in order; "shime1" is always the last resort.
FALLBACKS: dict[str, tuple[str, ...]] = {
    "shime2": _chain(3),
    "shime3": _chain(2),
    "shime22": _chain(4),
    "shime5": _chain(6),
    "shime6": _chain(5),
    "shime9": _chain(7),
    "shime10": _chain(8),
    "shime12": _chain(13, 14),
    "shime13": _chain(14, 12),
    "shime14": _chain(13, 12),
    "shime18": _chain(19),
    "shime19": _chain(18),
    "shime20": _chain(21, 11),
    "shime21": _chain(20, 11),
    "shime23": _chain(24, 25),
    "shime24": _chain(23, 25),
    "shime25": _chain(23, 24),
    "shime26": _chain(11),
    "shime30": _chain(11),
    "shime31": _chain(30, 11),
    "shime32": _chain(31, 30, 11),
    "shime33": _chain(31, 30, 11),
    **{f"shime{n}": _chain(26, 11) for n in (15, 16, 17, 27, 28, 29)},
}


def resolve(name: str, available: set[str]) -> str:
    """Return the frame to draw for `name` given the frames that exist."""
    if name in available:
        return name
    if name.startswith("talk"):
        candidates: tuple[str, ...] = ("talk1",)
    elif name.startswith("think"):
        candidates = ("think1", "shime26", "shime11")
    else:
        candidates = FALLBACKS.get(name, ())
    for candidate in candidates:
        if candidate in available:
            return candidate
    return "shime1"
