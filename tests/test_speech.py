import random
from datetime import datetime

import pytest

from phoebe_pet.speech import Speaker

LINES = {"sleepy": ("A", "B"), "calm": ("차분해요.",), "thrown": ("앗!",)}


def at(h, m, day=20):
    return datetime(2026, 11, day, h, m)


def make(lines=None, gap=(4, 10), now=None):
    return Speaker(LINES if lines is None else lines, random.Random(0), gap, now or at(9, 0))


@pytest.fixture
def speaker():
    return make()


def test_mood_line_due_after_gap(speaker):
    speaker.tick(3 * 60, "calm"); assert speaker.due() is None
    speaker.tick(8 * 60, "calm"); assert speaker.due() == "calm"


def test_bored_speaks_sooner_than_sleepy():
    fast, slow = make(gap=(10, 10)), make(gap=(10, 10))
    fast.tick(7 * 60, "bored"); slow.tick(14 * 60, "sleepy")
    assert fast.due() == "bored" and slow.due() is None


def test_seconds_until_due_scales_with_mood():
    s = make(gap=(10, 10))
    s.tick(60, "calm")
    assert s.seconds_until_due("calm") == 540 and s.seconds_until_due("bored") == 300
    s.tick(600, "calm")
    assert s.seconds_until_due("calm") == 0.0 and s.quiet_seconds == 660


def test_event_waits_a_moment_then_wins(speaker):
    speaker.note_event("thrown", clock=100.0); assert speaker.due() is None
    speaker.tick(5.0, "calm"); assert speaker.due() == "thrown"


def test_newer_event_replaces_unfired_and_drop_forgets(speaker):
    speaker.note_event("thrown", 100.0); speaker.note_event("woke", 101.0)
    speaker.tick(5.0, "calm"); assert speaker.due() == "woke"
    speaker.drop_pending(); assert speaker.due() is None


def test_event_cooldown(speaker):
    speaker.note_event("thrown", 100.0); speaker.tick(5, "calm"); speaker.spoke("앗")
    speaker.note_event("thrown", 400.0); speaker.tick(5, "calm"); assert speaker.due() is None
    speaker.note_event("thrown", 800.0); speaker.tick(5, "calm"); assert speaker.due() == "thrown"


def test_clock_events_once_per_day():
    s = make(now=at(11, 0))
    assert s.clock_event(at(11, 59)) is None and s.clock_event(at(12, 0)) == "lunch" and s.clock_event(at(12, 30)) is None
    assert s.clock_event(at(18, 1)) == "evening" and s.clock_event(at(23, 5)) == "late_night"
    assert s.clock_event(at(1, 0, day=21)) is None  # still the 20th's night
    assert s.clock_event(at(12, 0, day=21)) == "lunch"


def test_clock_events_skip_hours_past_at_start():
    assert make(now=at(19, 0)).clock_event(at(19, 1)) is None


def test_clean_cuts_to_first_sentence_and_60_chars(speaker):
    assert speaker.clean("구름이 예뻐요. 그리고 또...") == "구름이 예뻐요."
    assert speaker.clean('"하암..."') == "하암..."
    long = "가" * 80
    assert speaker.clean(long) == "가" * 59 + "…"


def test_clean_rejects_code_and_empty(speaker):
    assert speaker.clean("  ") is None and speaker.clean("```py\nx\n```") is None


def test_clean_rejects_recent_repeat(speaker):
    speaker.spoke("하암, 졸려요."); assert speaker.clean("하암, 졸려요.") is None


def test_fallback_avoids_recent_and_handles_missing():
    s = make(lines={"sleepy": ("A", "B")}); s.spoke("A")
    assert s.fallback("sleepy") == "B" and s.fallback("bored") is None


def test_spoke_restarts_the_gap(speaker):
    speaker.tick(11 * 60, "calm"); assert speaker.due() == "calm"
    speaker.spoke("안녕"); assert speaker.due() is None and speaker.quiet_seconds == 0


def test_situation_mentions_time_mood_and_event(speaker):
    text = speaker.situation("thrown", "sulky", "stand", at(23, 20), 600)
    assert "오후 11시 20분" in text and "10분" in text and text.startswith("(") and text.endswith(")")
    assert "시무룩" in text and "던졌" in text
    assert "서 있다" in speaker.situation("calm", "calm", "stand", at(0, 5), 0)


def test_dropped_or_replaced_event_does_not_start_cooldown(speaker):
    speaker.note_event("thrown", 100.0); speaker.drop_pending()
    speaker.note_event("thrown", 200.0); speaker.tick(5, "calm"); assert speaker.due() == "thrown"
    s = make()
    s.note_event("thrown", 100.0); s.note_event("woke", 101.0)
    s.note_event("thrown", 102.0); s.tick(5, "calm"); assert s.due() == "thrown"


def test_clean_rejects_long_repeat_and_letterless(speaker):
    speaker.spoke("가" * 59 + "…")
    assert speaker.clean("가" * 80) is None and speaker.clean("...음") is None


def test_situation_under_a_minute_has_no_zero_minutes(speaker):
    assert "0분째" not in speaker.situation("calm", "calm", "stand", at(9, 0), 30)


PHOEBE_ACTIONS = (
    "to_walk", "to_run", "from_walk", "sit_down", "stand_up", "lie_down", "get_up", "wake_up",
    "creep", "sit_dangle", "sit_spin", "look_up", "wall_hold", "wall_climb", "ceiling_hold",
    "ceiling_move",
)


@pytest.mark.parametrize("action", PHOEBE_ACTIONS)
def test_situation_describes_the_phoebe_actions(speaker, action):
    assert "그냥 있다" not in speaker.situation("calm", "calm", action, at(9, 0), 0)
