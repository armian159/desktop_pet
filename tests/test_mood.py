from datetime import datetime

import pytest

from phoebe_pet.mood import Mood


def at(h, m=0):
    return datetime(2026, 11, 20, h, m)


def test_start_energy_follows_time_of_day():
    assert Mood(at(8)).energy == 0.8 and Mood(at(14)).energy == 0.6 and Mood(at(20)).energy == 0.45 and Mood(at(2)).energy == 0.3


def test_awake_energy_drops_and_sleep_restores():
    m = Mood(at(14)); m.tick(3600, "stand", at(15), False); assert m.energy == pytest.approx(0.45)
    m.tick(3600, "lie", at(16), False); assert m.energy == pytest.approx(1.0)  # clamped


def test_night_and_running_drain_faster():
    m = Mood(at(14)); m.energy = 0.9; m.tick(3600, "run", at(1), False); assert m.energy == pytest.approx(0.3)


def test_boredom_rises_alone_and_falls_with_mouse_near():
    m = Mood(at(14)); m.tick(3600, "stand", at(15), False); assert m.boredom == pytest.approx(0.7)
    m.tick(3600, "stand", at(16), True); assert m.boredom == pytest.approx(0.2)


def test_cheer_drifts_back_to_resting_value():
    m = Mood(at(14)); m.cheer = 0.1; m.tick(3600, "stand", at(15), False); assert m.cheer == pytest.approx(0.3)
    m.cheer = 0.65; m.tick(3600, "stand", at(16), False); assert m.cheer == pytest.approx(0.6)


def test_events():
    m = Mood(at(14)); m.on_throw(299); assert m.cheer == 0.6
    m.on_throw(800); assert m.cheer == pytest.approx(0.35)
    m.on_resist(0.5); assert m.cheer == pytest.approx(0.35)
    m.on_resist(2.0); assert m.cheer == pytest.approx(0.25)
    m.boredom = 0.9; m.on_chat_done(); assert m.boredom == pytest.approx(0.4) and m.cheer == pytest.approx(0.4)
    m.on_interact(); assert m.boredom == pytest.approx(0.1)


def test_name_priority():
    m = Mood(at(14)); assert m.name == "calm"
    m.cheer = 0.9; assert m.name == "happy"
    m.boredom = 0.8; assert m.name == "bored"
    m.cheer = 0.2; assert m.name == "sulky"
    m.energy = 0.1; assert m.name == "sleepy"


def test_name_has_hysteresis():
    m = Mood(at(14)); m.energy = 0.29; assert m.name == "sleepy"
    m.energy = 0.33; assert m.name == "sleepy"
    m.energy = 0.36; assert m.name == "calm"
    m.energy = 0.32; assert m.name == "calm"


def test_forced_name_wins():
    m = Mood(at(14)); m.forced = "bored"; assert m.name == "bored"
