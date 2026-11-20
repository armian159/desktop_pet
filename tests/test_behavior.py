import random
from pathlib import Path

import pytest

from phoebe_pet.behavior import Chooser, load_actions

ROOT = Path(__file__).resolve().parent.parent
ACTIONS = load_actions(ROOT / "actions.toml")

GOOD = """
[action.a]
surface = "floor"
frames = ["shime1"]
frame_ms = 100
speed = 0
duration = [1, 2]
weight = 1
idle_weight = 1
next = ["a"]
"""


def write(tmp_path, text):
    p = tmp_path / "actions.toml"
    p.write_text(text, encoding="utf-8")
    return p


def test_repo_actions_file_loads_and_has_core_actions():
    assert {"stand", "walk", "sit", "lie", "wall_climb", "ceiling_move", "fall", "drag", "talk", "think"} <= set(ACTIONS)


def test_resting_is_derived_from_speed():
    assert ACTIONS["sit"].resting and not ACTIONS["walk"].resting


def test_offset_defaults_to_zero_and_reads_override():
    assert ACTIONS["stand"].offset == (0, 0) and ACTIONS["wall_hold"].offset == (-64, 0)


def test_minimal_file_loads(tmp_path):
    assert set(load_actions(write(tmp_path, GOOD))) == {"a"}


def test_unknown_next_reference_rejected(tmp_path):
    with pytest.raises(ValueError, match="nope"):
        load_actions(write(tmp_path, GOOD.replace('next = ["a"]', 'next = ["nope"]')))


def test_empty_frames_rejected(tmp_path):
    with pytest.raises(ValueError, match="frames"):
        load_actions(write(tmp_path, GOOD.replace('frames = ["shime1"]', "frames = []")))


def test_empty_next_rejected(tmp_path):
    with pytest.raises(ValueError, match="next"):
        load_actions(write(tmp_path, GOOD.replace('next = ["a"]', "next = []")))


def test_missing_key_names_action_and_key(tmp_path):
    with pytest.raises(ValueError, match="a.*speed"):
        load_actions(write(tmp_path, GOOD.replace("speed = 0\n", "")))


def test_bad_surface_rejected(tmp_path):
    with pytest.raises(ValueError, match="surface"):
        load_actions(write(tmp_path, GOOD.replace('"floor"', '"moon"')))


def test_choice_always_comes_from_next():
    c = Chooser(ACTIONS, random.Random(1))
    for _ in range(500):
        assert c.choose("walk", 0) == "stand"
    assert {c.choose("sit", 0) for _ in range(500)} == {"stand", "sit_spin", "sit_dangle", "lie"}


def test_no_immediate_repeat_when_alternatives_exist():
    c = Chooser(ACTIONS, random.Random(2))
    assert "stand" not in {c.choose("stand", 0) for _ in range(500)}


def test_repeat_allowed_when_it_is_the_only_option(tmp_path):
    c = Chooser(load_actions(write(tmp_path, GOOD)), random.Random(0))
    assert c.choose("a", 0) == "a"


def test_idle_shifts_toward_resting():
    def share(idle):
        c = Chooser(ACTIONS, random.Random(3))
        return sum(c.choose("stand", idle) == "sit" for _ in range(4000)) / 4000

    assert share(120) > share(0) + 0.15


def test_duration_within_range():
    c = Chooser(ACTIONS, random.Random(4))
    assert all(2 <= c.duration("walk") <= 8 for _ in range(200))


REPO_TEXT = (ROOT / "actions.toml").read_text(encoding="utf-8")


def test_real_app_needs_its_fixed_actions(tmp_path):
    from phoebe_pet.behavior import REQUIRED, check_complete

    check_complete(ACTIONS)
    assert {"stand", "fall", "land", "drag", "resist", "think", "talk", "look_at_mouse", "wall_hold", "ceiling_hold"} <= REQUIRED
    broken = dict(ACTIONS)
    del broken["drag"]
    with pytest.raises(ValueError, match="drag"):
        check_complete(broken)


def test_empty_file_is_reported_not_crashed(tmp_path):
    from phoebe_pet.behavior import check_complete

    with pytest.raises(ValueError, match="stand"):
        check_complete(load_actions(write(tmp_path, "")))


@pytest.mark.parametrize(
    "old, new",
    [
        ("\nweight = 1", '\nweight = "6"'),
        ("duration = [1, 2]", "duration = [[1], 4]"),
        ("duration = [1, 2]", "duration = [1]"),
        ("frame_ms = 100", 'frame_ms = "fast"'),
        ('next = ["a"]', "next = 3"),
        ("speed = 0", 'speed = "slow"'),
    ],
)
def test_wrong_types_raise_value_error(tmp_path, old, new):
    assert old in GOOD
    with pytest.raises(ValueError):
        load_actions(write(tmp_path, GOOD.replace(old, new)))


def test_action_table_of_wrong_shape_raises_value_error(tmp_path):
    with pytest.raises(ValueError):
        load_actions(write(tmp_path, "action = 3"))


def test_next_must_stay_on_the_same_surface(tmp_path):
    text = REPO_TEXT.replace('next = ["walk", "run", "sit", "look_up", "stand"]', 'next = ["walk", "wall_hold"]')
    assert text != REPO_TEXT
    with pytest.raises(ValueError, match="wall_hold"):
        load_actions(write(tmp_path, text))


def test_duration_is_a_whole_number_of_loops():
    c = Chooser(ACTIONS, random.Random(5))
    walk = ACTIONS["walk"]
    loop = len(walk.frames) * walk.frame_ms / 1000
    for _ in range(200):
        loops = c.duration("walk") / loop
        assert loops >= 1 and abs(loops - round(loops)) < 1e-9


def test_intro_flag_defaults_off_and_reads_true(tmp_path):
    assert not ACTIONS["walk"].intro
    actions = load_actions(write(tmp_path, GOOD + "intro = true\n"))
    assert actions["a"].intro


def test_mood_affinity_multiplies_weight():
    # stand -> next has walk(5) and sit(2) among others; make sit dominant when sleepy
    rng = random.Random(1)
    c = Chooser(ACTIONS, rng, {"sit": {"sleepy": 1000}})
    picks = [c.choose("stand", 0, "sleepy") for _ in range(200)]
    assert picks.count("sit") > 190
    picks = [c.choose("stand", 0, "calm") for _ in range(200)]
    assert picks.count("sit") < 100


def test_affinity_for_unknown_action_is_ignored():
    Chooser(ACTIONS, random.Random(0), {"nope": {"sleepy": 3}}).choose("stand", 0, "sleepy")


def test_all_zero_after_affinity_falls_back_to_even():
    c = Chooser(ACTIONS, random.Random(0), {n: {"sleepy": 0} for n in ACTIONS})
    assert c.choose("stand", 0, "sleepy") in ACTIONS["stand"].next
