"""Decides when the pet speaks on its own and what, and tidies model replies. No Qt."""

from __future__ import annotations

import random
import re
from collections import deque
from datetime import datetime, timedelta

MAX_CHARS = 60
RECENT = 10
EVENT_COOLDOWN = 600.0
EVENT_DELAY = (2.0, 5.0)

_GAP_SCALE = {"bored": 0.6, "sleepy": 1.5}
# (hour the slot starts, event name), latest first.
_CLOCK_SLOTS = ((23, "late_night"), (18, "evening"), (12, "lunch"))
_SENTENCE = re.compile(r".*?(?:[.!?…~]+|\n|$)", re.DOTALL)
_QUOTES = "\"'“”‘’"

_MOOD_TEXT = {
    "sleepy": "많이 졸리다",
    "sulky": "조금 시무룩하다",
    "bored": "심심해서 몸이 근질거린다",
    "happy": "기분이 좋다",
    "calm": "차분하고 평온하다",
}
_EVENT_TEXT = {
    "thrown": "방금 누군가 페비를 휙 던졌다",
    "woke": "방금 잠에서 깼다",
    "released": "방금 붙잡혀 있다가 놓여났다",
    "lunch": "점심때가 되었다",
    "evening": "저녁때가 되었다",
    "late_night": "밤이 깊었다",
}
_ACTION_TEXT = {
    "stand": "가만히 서 있다",
    "sit": "앉아 있다",
    "lie": "누워 있다",
    "doze_off": "꾸벅꾸벅 졸고 있다",
    "walk": "걷고 있다",
    "run": "뛰어다니고 있다",
}


class Speaker:
    def __init__(
        self,
        lines: dict[str, tuple[str, ...]],
        rng: random.Random,
        gap_minutes: tuple[float, float],
        now: datetime,
    ) -> None:
        self._lines = lines
        self._rng = rng
        self._gap_minutes = gap_minutes
        self._quiet = 0.0
        self._gap = self._pick_gap()
        self._mood = "calm"
        self._recent: deque[str] = deque(maxlen=RECENT)
        self._pending: str | None = None
        self._delay = 0.0
        self._last_noted: dict[str, float] = {}
        self._fired: set[tuple[datetime, str]] = set()
        slot = self._slot(now)
        if slot is not None:
            self._fired.add(slot)

    @property
    def quiet_seconds(self) -> float:
        return self._quiet

    def tick(self, seconds: float, mood: str) -> None:
        self._mood = mood
        self._quiet += seconds
        if self._pending is not None:
            self._delay -= seconds

    def note_event(self, event: str, clock: float) -> None:
        last = self._last_noted.get(event)
        if last is not None and clock - last < EVENT_COOLDOWN:
            return
        self._last_noted[event] = clock
        self._pending = event
        self._delay = self._rng.uniform(*EVENT_DELAY)

    def clock_event(self, now: datetime) -> str | None:
        slot = self._slot(now)
        if slot is None or slot in self._fired:
            return None
        self._fired.add(slot)
        return slot[1]

    def due(self) -> str | None:
        if self._pending is not None and self._delay <= 0:
            return self._pending
        if self.seconds_until_due(self._mood) <= 0:
            return self._mood
        return None

    def seconds_until_due(self, mood: str) -> float:
        """Seconds until a mood line is due at that mood's gap scaling; 0 if already due."""
        return max(0.0, self._gap * _GAP_SCALE.get(mood, 1.0) - self._quiet)

    def drop_pending(self) -> None:
        self._pending = None

    def reset_quiet(self) -> None:
        self._quiet = 0.0
        self._gap = self._pick_gap()

    def situation(
        self, key: str, mood: str, action: str, now: datetime, quiet_seconds: float
    ) -> str:
        period = "오전" if now.hour < 12 else "오후"
        hour = now.hour % 12 or 12
        what = _EVENT_TEXT.get(key) or _ACTION_TEXT.get(action, "그냥 있다")
        return (
            f"(지금은 {period} {hour}시 {now.minute}분. "
            f"페비는 {_MOOD_TEXT.get(mood, _MOOD_TEXT['calm'])}. {what}. "
            f"방랑자님은 {int(quiet_seconds // 60)}분째 말이 없다. "
            "페비가 혼잣말처럼 짧게 한 문장만 말한다. 20자 안팎.)"
        )

    def clean(self, reply: str) -> str | None:
        if "```" in reply:
            return None
        sentence = _SENTENCE.match(reply.strip()).group(0).strip().strip(_QUOTES).strip()
        if not sentence or sentence in self._recent:
            return None
        if len(sentence) > MAX_CHARS:
            sentence = sentence[: MAX_CHARS - 1] + "…"
        return sentence

    def fallback(self, key: str) -> str | None:
        options = self._lines.get(key)
        if not options:
            return None
        fresh = [line for line in options if line not in self._recent]
        return self._rng.choice(fresh or list(options))

    def spoke(self, line: str) -> None:
        self._recent.append(line)
        if self._pending is not None and self._delay <= 0:
            self._pending = None
        self.reset_quiet()

    def _pick_gap(self) -> float:
        return self._rng.uniform(*self._gap_minutes) * 60

    @staticmethod
    def _slot(now: datetime) -> tuple[datetime, str] | None:
        """The clock slot now falls in, keyed by the date its day started on."""
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if now.hour < 5:
            return midnight - timedelta(days=1), "late_night"
        for hour, name in _CLOCK_SLOTS:
            if now.hour >= hour:
                return midnight, name
        return None
