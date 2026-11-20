"""The pet's brain: where it is, what it is doing, which frame shows. No Qt."""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass
from enum import Enum

from .behavior import Action, Chooser
from .physics import MAX_DT, Body, Bounds, Contact, clamp, on_floor, step_air

EASE = 0.3  # s to reach or leave walking speed
LAND_TIME = 0.4  # s of squash frames after touching down
GRAB_SPEED = 300.0  # px/s needed to catch a wall or ceiling in flight
LET_GO_CHANCE = 0.15
WALL_GRAB_CHANCE = 0.5
LOOK_RADIUS = 200.0
DRAG_WINDOW = 0.1  # s of cursor history used to estimate throw speed
DRAG_TILT_SPEED = 1200.0  # px/s that gives the strongest lean
STILL_SPEED = 30.0
RESIST_AFTER = 1.0
CELL = 128  # frame size the offsets in actions.toml are written for


class Mode(Enum):
    AUTO = "auto"
    AIR = "air"
    DRAGGED = "dragged"
    THINK = "think"
    TALK = "talk"
    PAUSED = "paused"


@dataclass(frozen=True)
class View:
    x: int
    y: int
    frame: str
    facing_right: bool
    resting: bool
    offset: tuple[int, int] = (0, 0)  # where to draw the image relative to (x, y)


class Pet:
    def __init__(
        self,
        actions: dict[str, Action],
        chooser: Chooser,
        bounds: Bounds,
        size: tuple[int, int],
        rng: random.Random,
        speed: float = 1.0,
    ) -> None:
        self._actions = actions
        self._chooser = chooser
        self._bounds = bounds
        self._rng = rng
        self._speed = speed
        w, h = size
        x = rng.uniform(bounds.left, max(bounds.left, bounds.right - w))
        self._body = Body(x, bounds.bottom - h, 0.0, 0.0, w, h)
        clamp(self._body, bounds)
        self.mode = Mode.AUTO
        self.action = "stand"
        self.idle_seconds = 0.0
        self._facing_right = rng.random() < 0.5
        self._paused = False
        self._pending_chat: Mode | None = None
        self._wall_left = True
        self._climb_dir = -1
        self._elapsed = 0.0
        self._duration = 0.0
        self._land_left = 0.0
        self._drag: deque[tuple[float, float, float]] = deque()
        self._drag_clock = 0.0
        self._drag_v = (0.0, 0.0)
        self._still = 0.0
        self._start("stand")

    # ---- public --------------------------------------------------------

    def tick(self, dt: float, mouse: tuple[int, int]) -> View:
        dt = max(0.0, min(dt, MAX_DT))
        self.idle_seconds += dt
        self._elapsed += dt
        if self.mode is Mode.AUTO:
            self._tick_auto(dt)
        elif self.mode is Mode.AIR:
            self._tick_air(dt)
        elif self.mode is Mode.DRAGGED:
            self.drag_to(mouse, dt)
        return self._view(mouse)

    def grab(self, mouse: tuple[int, int]) -> None:
        if self.mode in (Mode.THINK, Mode.TALK):
            self._pending_chat = self.mode
        self.mode = Mode.DRAGGED
        self.action = "drag"
        self._drag.clear()
        self._drag_clock = 0.0
        self._drag_v = (0.0, 0.0)
        self._still = 0.0
        self._elapsed = 0.0
        self.touch()
        self.drag_to(mouse, 0.0)

    def drag_to(self, mouse: tuple[int, int], dt: float) -> None:
        if self.mode is not Mode.DRAGGED:
            return
        mx, my = mouse
        self._body.x = mx - self._body.w / 2
        self._body.y = my
        clamp(self._body, self._bounds)
        self._drag_clock += max(0.0, dt)
        self._drag.append((self._drag_clock, mx, my))
        while len(self._drag) > 2 and self._drag_clock - self._drag[0][0] > DRAG_WINDOW:
            self._drag.popleft()
        t0, x0, y0 = self._drag[0]
        span = self._drag_clock - t0
        self._drag_v = ((mx - x0) / span, (my - y0) / span) if span > 0 else (0.0, 0.0)
        if math.hypot(*self._drag_v) < STILL_SPEED:
            self._still += max(0.0, dt)
        else:
            self._still = 0.0
        self.touch()

    def release(self) -> None:
        if self.mode is not Mode.DRAGGED:
            return
        vx, vy = self._drag_v
        if vx:
            self._facing_right = vx > 0
        self._drop(vx, vy)

    def begin_think(self) -> None:
        self.touch()
        self._enter_chat(Mode.THINK)

    def begin_talk(self) -> None:
        self._enter_chat(Mode.TALK)

    def end_chat(self) -> None:
        self._pending_chat = None
        if self.mode in (Mode.THINK, Mode.TALK):
            self._resume()

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        if paused and self.mode is Mode.AUTO:
            if self._surface() == "floor":
                self._resume()
            else:
                self._drop()
        elif not paused and self.mode is Mode.PAUSED:
            self._resume()

    def set_bounds(self, bounds: Bounds) -> None:
        self._bounds = bounds
        clamp(self._body, bounds)
        if self.mode in (Mode.AIR, Mode.DRAGGED) or self._attached():
            return
        if self.mode in (Mode.THINK, Mode.TALK):
            self._pending_chat = self.mode
        self._drop()

    def touch(self) -> None:
        self.idle_seconds = 0.0

    # ---- test and internal entry points ---------------------------------

    def _start(self, name: str) -> None:
        self.action = name
        self._elapsed = 0.0
        action = self._actions[name]
        self._duration = self._chooser.duration(name) if action.next else 1.0
        if action.speed and action.surface == "floor":
            b, body = self._bounds, self._body
            if body.x <= b.left:
                self._facing_right = True
            elif body.x >= b.right - body.w:
                self._facing_right = False
            elif self._rng.random() < 0.3:
                self._facing_right = not self._facing_right
        elif action.speed and action.surface == "wall":
            b, body = self._bounds, self._body
            if body.y <= b.top:
                self._climb_dir = 1
            elif on_floor(body, b):
                self._climb_dir = -1
            else:
                self._climb_dir = -1 if self._rng.random() < 0.7 else 1

    def _place_on_wall(self, left: bool, y: float | None = None) -> None:
        b, body = self._bounds, self._body
        self._wall_left = left
        self._facing_right = not left
        body.x = b.left if left else b.right - body.w
        if y is not None:
            body.y = y
        body.vx = body.vy = 0.0
        clamp(body, b)
        self.mode = Mode.AUTO
        self._start("wall_hold")

    # ---- modes ----------------------------------------------------------

    def _surface(self) -> str:
        return self._actions[self.action].surface

    def _attached(self) -> bool:
        b, body = self._bounds, self._body
        surface = self._surface() if self.mode is Mode.AUTO else "floor"
        if surface == "wall":
            return body.x == (b.left if self._wall_left else max(b.left, b.right - body.w))
        if surface == "ceiling":
            return body.y == b.top
        return on_floor(body, b)

    def _drop(self, vx: float = 0.0, vy: float = 0.0) -> None:
        self._body.vx, self._body.vy = vx, vy
        self.mode = Mode.AIR
        self.action = "fall"
        self._elapsed = 0.0
        self._land_left = 0.0

    def _resume(self) -> None:
        """Back to normal life on the floor (or to standing still if paused)."""
        self.mode = Mode.PAUSED if self._paused else Mode.AUTO
        self._start("stand")

    def _enter_chat(self, mode: Mode) -> None:
        if self.mode in (Mode.THINK, Mode.TALK):
            self.mode = mode
            self._set_special(mode.value)
        elif self.mode in (Mode.AIR, Mode.DRAGGED):
            self._pending_chat = mode
        elif self._surface() == "floor":
            self.mode = mode
            self._set_special(mode.value)
        else:
            self._pending_chat = mode
            self._drop()

    def _set_special(self, name: str) -> None:
        self.action = name
        self._elapsed = 0.0

    def _tick_auto(self, dt: float) -> None:
        action = self._actions[self.action]
        b, body = self._bounds, self._body
        if action.speed:
            ramp = min(1.0, self._elapsed / EASE, max(0.0, self._duration - self._elapsed) / EASE)
            step = action.speed * self._speed * ramp * dt
            if action.surface == "floor":
                body.x += step if self._facing_right else -step
                hit_left, hit_right = body.x <= b.left, body.x >= b.right - body.w
                if hit_left or hit_right:
                    clamp(body, b)
                    if self._rng.random() < WALL_GRAB_CHANCE:
                        self._place_on_wall(left=hit_left)
                    else:
                        self._facing_right = hit_left
                        self._start("stand")
                    return
            elif action.surface == "wall":
                body.y += step * self._climb_dir
                if body.y <= b.top:
                    clamp(body, b)
                    self._facing_right = self._wall_left
                    self._start("ceiling_hold")
                    return
                if on_floor(body, b):
                    clamp(body, b)
                    self._facing_right = self._wall_left
                    self._start("stand")
                    return
            else:
                body.x += step if self._facing_right else -step
                if body.x <= b.left or body.x >= b.right - body.w:
                    clamp(body, b)
                    self._facing_right = body.x <= b.left
        if self._elapsed >= self._duration:
            if action.surface != "floor" and not action.speed and self._rng.random() < LET_GO_CHANCE:
                self._drop()
            else:
                self._start(self._chooser.choose(self.action, self.idle_seconds))

    def _tick_air(self, dt: float) -> None:
        body = self._body
        if self.action == "land":
            self._land_left -= dt
            if self._land_left <= 0:
                pending, self._pending_chat = self._pending_chat, None
                if pending is not None:
                    self.mode = pending
                    self._set_special(pending.value)
                else:
                    self._resume()
            return
        vx, vy = body.vx, body.vy
        contact = step_air(body, self._bounds, dt)
        if contact is Contact.FLOOR:
            body.vx = 0.0
            self._set_special("land")
            self._land_left = LAND_TIME
            return
        free = self._pending_chat is None and not self._paused
        if contact in (Contact.LEFT_WALL, Contact.RIGHT_WALL) and free and abs(vx) >= GRAB_SPEED:
            self._place_on_wall(left=contact is Contact.LEFT_WALL)
        elif contact is Contact.CEILING and free and abs(vy) >= GRAB_SPEED:
            body.vx = 0.0
            self.mode = Mode.AUTO
            self._start("ceiling_hold")

    # ---- what to draw -----------------------------------------------------

    def _frame(self, name: str) -> str:
        action = self._actions[name]
        return action.frames[int(self._elapsed * 1000 / action.frame_ms) % len(action.frames)]

    def _view(self, mouse: tuple[int, int]) -> View:
        body = self._body
        x, y = round(body.x), round(body.y)
        facing = self._facing_right
        if self.mode is Mode.DRAGGED:
            if self._still >= RESIST_AFTER:
                frame = self._frame("resist")
            else:
                frames = self._actions["drag"].frames
                lean = (self._drag_v[0] + DRAG_TILT_SPEED) / (2 * DRAG_TILT_SPEED)
                frame = frames[max(0, min(len(frames) - 1, int(lean * len(frames))))]
            return View(x, y, frame, False, False)
        if self.mode is Mode.PAUSED:
            return View(x, y, self._frame("stand"), facing, True)
        if self.mode is not Mode.AUTO:
            return View(x, y, self._frame(self.action), facing, False)
        action = self._actions[self.action]
        frame = self._frame(self.action)
        resting = action.resting
        if self.action in ("stand", "sit"):
            cx, cy = body.x + body.w / 2, body.y + body.h / 2
            if math.hypot(mouse[0] - cx, mouse[1] - cy) < LOOK_RADIUS:
                facing = mouse[0] > cx
                resting = False
                if self.action == "sit":
                    frame = self._frame("look_at_mouse")
        dx = round(action.offset[0] * body.w / CELL)
        dy = round(action.offset[1] * body.h / CELL)
        return View(x, y, frame, facing, resting, (-dx if facing else dx, dy))
