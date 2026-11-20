"""Airborne motion inside the screen's work area. No Qt here."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

GRAVITY = 2400.0  # px/s^2
MAX_SPEED = 3000.0  # px/s per axis
MAX_DT = 0.05  # s; longer gaps (sleep, stalls) are cut down to this


@dataclass(frozen=True)
class Bounds:
    left: int
    top: int
    right: int
    bottom: int


@dataclass
class Body:
    x: float  # top-left corner
    y: float
    vx: float
    vy: float
    w: int
    h: int


class Contact(Enum):
    NONE = 0
    FLOOR = 1
    LEFT_WALL = 2
    RIGHT_WALL = 3
    CEILING = 4


def _limit(value: float, low: float, high: float) -> float:
    return max(low, min(value, max(low, high)))


def clamp(body: Body, bounds: Bounds) -> None:
    """Pull the body inside; bounds smaller than the body pin it to top-left."""
    body.x = _limit(body.x, bounds.left, bounds.right - body.w)
    body.y = _limit(body.y, bounds.top, bounds.bottom - body.h)


def on_floor(body: Body, bounds: Bounds) -> bool:
    return body.y >= bounds.bottom - body.h


def step_air(body: Body, bounds: Bounds, dt: float) -> Contact:
    """Apply gravity for dt seconds and stop at whichever edge is hit."""
    dt = _limit(dt, 0.0, MAX_DT)
    body.vx = _limit(body.vx, -MAX_SPEED, MAX_SPEED)
    body.vy = _limit(body.vy + GRAVITY * dt, -MAX_SPEED, MAX_SPEED)
    x = body.x + body.vx * dt
    y = body.y + body.vy * dt
    body.x, body.y = x, y
    clamp(body, bounds)
    hit_x, hit_y = body.x != x, body.y != y
    if hit_x:
        body.vx = 0.0
    if hit_y:
        body.vy = 0.0
    if hit_y and y > body.y:
        return Contact.FLOOR
    if hit_y:
        return Contact.CEILING
    if hit_x:
        return Contact.LEFT_WALL if x < body.x else Contact.RIGHT_WALL
    return Contact.NONE
