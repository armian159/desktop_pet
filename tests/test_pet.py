import dataclasses
import random
from pathlib import Path

import pytest

from phoebe_pet.behavior import Chooser, load_actions
from phoebe_pet.pet import Mode, Pet
from phoebe_pet.physics import MAX_DT, Bounds

ROOT = Path(__file__).resolve().parent.parent
ACTIONS = load_actions(ROOT / "actions.toml")
B = Bounds(0, 0, 1920, 1040)
FAR = (-9999, -9999)
FLOOR_Y = 1040 - 128


def make(seed=0, bounds=B):
    rng = random.Random(seed)
    return Pet(ACTIONS, Chooser(ACTIONS, rng), bounds, (128, 128), rng)


def run(pet, seconds, mouse=FAR, dt=1 / 60):
    return [pet.tick(dt, mouse) for _ in range(int(seconds / dt))]


def test_starts_standing_on_floor():
    v = make().tick(0.0, FAR)
    assert v.y == FLOOR_Y and v.frame == "shime1"


@pytest.mark.parametrize("seed", range(20))
def test_ten_minutes_never_leaves_bounds_and_visits_variety(seed):
    pet = make(seed)
    seen = set()
    for _ in range(600 * 60):
        v = pet.tick(1 / 60, FAR)
        assert 0 <= v.x <= 1920 - 128 and 0 <= v.y <= FLOOR_Y
        seen.add(pet.action)
    assert len(seen) >= 6


def test_some_seed_reaches_wall_and_ceiling():
    seen = set()
    for seed in range(20):
        pet = make(seed)
        for _ in range(600 * 60):
            pet.tick(1 / 60, FAR)
            seen.add(pet.action)
    assert {"wall_climb", "ceiling_move", "fall", "land"} <= seen


def test_floor_actions_keep_feet_on_floor():
    pet = make(5)
    for _ in range(120 * 60):
        v = pet.tick(1 / 60, FAR)
        if pet.mode is Mode.AUTO and pet.action in ("walk", "run", "sit", "lie", "creep"):
            assert v.y == FLOOR_Y


def test_walk_eases_in():
    pet = make()
    pet._start("walk")
    xs = [v.x for v in run(pet, 0.5)]
    first, later = abs(xs[5] - xs[0]), abs(xs[29] - xs[24])
    assert first < later


def test_grab_drag_release_throws_and_lands():
    pet = make()
    pet.grab((960, 500))
    for i in range(10):
        pet.drag_to((960 + i * 30, 500), 1 / 60)
    assert pet.mode is Mode.DRAGGED
    pet.release()
    assert pet.mode is Mode.AIR
    views = run(pet, 5)
    assert views[5].x > 960 and pet.mode is Mode.AUTO


def test_drag_frame_follows_horizontal_speed():
    pet = make()
    pet.grab((960, 500))
    for i in range(10):
        pet.drag_to((960 + i * 30, 500), 1 / 60)
    fast_right = pet.tick(1 / 60, (1260, 500)).frame
    for _ in range(30):
        pet.drag_to((1260, 500), 1 / 60)
    still = pet.tick(1 / 60, (1260, 500)).frame
    assert fast_right == "shime9" and still == "shime1"


def test_held_still_starts_struggling():
    pet = make()
    pet.grab((960, 500))
    frames = {v.frame for v in run(pet, 2.5, mouse=(960, 500))}
    assert {"shime5", "shime6"} <= frames


def test_slow_release_falls_straight_down():
    pet = make()
    pet.grab((960, 300))
    run(pet, 0.5, mouse=(960, 300))
    pet.release()
    views = run(pet, 3)
    assert {v.x for v in views[:10]} == {960 - 64} and views[-1].y == FLOOR_Y


def test_hard_throw_at_wall_grabs_it():
    pet = make()
    pet.grab((1700, 500))
    for i in range(10):
        pet.drag_to((1700 + i * 15, 500), 1 / 60)
    pet.release()
    run(pet, 0.5)
    assert pet.mode is Mode.AUTO and pet.action in ("wall_hold", "wall_climb")
    assert pet.tick(1 / 60, FAR).offset == (64, 0)


def test_chat_stops_wandering_then_resumes():
    pet = make()
    pet.begin_think()
    views = run(pet, 3)
    assert pet.mode is Mode.THINK and len({v.x for v in views}) == 1
    assert {v.frame for v in views} == {"think1", "think2"}
    pet.begin_talk()
    assert pet.tick(1 / 60, FAR).frame.startswith("talk")
    pet.end_chat()
    assert pet.mode is Mode.AUTO


def test_think_from_wall_drops_to_floor_first():
    pet = make()
    pet._place_on_wall(left=True, y=300)
    pet.begin_think()
    run(pet, 3)
    assert pet.mode is Mode.THINK and pet.tick(1 / 60, FAR).y == FLOOR_Y


def test_reply_arriving_mid_fall_talks_after_landing():
    pet = make()
    pet._place_on_wall(left=True, y=300)
    pet.begin_think()
    pet.begin_talk()
    run(pet, 3)
    assert pet.mode is Mode.TALK


def test_end_chat_mid_fall_cancels_pending_chat():
    pet = make()
    pet._place_on_wall(left=True, y=300)
    pet.begin_think()
    pet.end_chat()
    run(pet, 3)
    assert pet.mode is Mode.AUTO


def test_paused_does_not_move_but_can_be_dragged():
    pet = make()
    pet.set_paused(True)
    assert pet.mode is Mode.PAUSED
    assert len({(v.x, v.y) for v in run(pet, 30)}) == 1
    pet.grab((500, 500))
    assert pet.mode is Mode.DRAGGED
    pet.release()
    run(pet, 3)
    assert pet.mode is Mode.PAUSED
    pet.set_paused(False)
    assert pet.mode is Mode.AUTO


def test_set_bounds_pulls_pet_inside():
    pet = make()
    pet.set_bounds(Bounds(0, 0, 800, 600))
    v = pet.tick(1 / 60, FAR)
    assert 0 <= v.x <= 800 - 128 and 0 <= v.y <= 600 - 128
    run(pet, 5)
    assert pet.tick(1 / 60, FAR).y == 600 - 128


def test_set_bounds_growing_drops_pet_to_new_floor():
    pet = make()
    pet.set_bounds(Bounds(0, 0, 1920, 1080))
    run(pet, 3)
    assert pet.tick(1 / 60, FAR).y == 1080 - 128


def test_long_gap_does_not_teleport():
    pet = make()
    a = pet.tick(1 / 60, FAR)
    b = pet.tick(3600.0, FAR)
    assert abs(b.x - a.x) <= 180 * MAX_DT + 1


def test_resting_flag():
    pet = make()
    pet._start("sit")
    assert pet.tick(1 / 60, FAR).resting
    pet._start("walk")
    assert not pet.tick(1 / 60, FAR).resting
    pet._start("sit")
    cx = pet.tick(1 / 60, FAR).x + 64
    assert not pet.tick(1 / 60, (cx + 50, 1000)).resting


def test_sitting_pet_looks_toward_nearby_mouse():
    pet = make()
    pet._start("sit")
    cx = pet.tick(1 / 60, FAR).x + 64
    v = pet.tick(1 / 60, (cx + 80, 900))
    assert v.frame == "shime26" and v.facing_right


def test_touch_resets_idle():
    pet = make()
    run(pet, 90)
    assert pet.idle_seconds > 60
    pet.touch()
    assert pet.idle_seconds == 0


def test_tiny_bounds_do_not_crash():
    pet = make(bounds=Bounds(0, 0, 100, 100))
    run(pet, 60)


# ---- forcing an action (developer panel) --------------------------------------


def test_force_starts_a_floor_action_on_the_floor(pet):
    from phoebe_pet.pet import Mode

    pet._place_on_wall(left=True, y=300)
    pet.force("walk")
    assert (pet.mode, pet.action) == (Mode.AUTO, "walk")
    assert pet._body.y == pet._bounds.bottom - pet._body.h


def test_force_puts_wall_and_ceiling_actions_on_their_surface(pet):
    pet.force("wall_climb")
    assert pet.action == "wall_climb"
    assert pet._body.x in (pet._bounds.left, pet._bounds.right - pet._body.w)
    pet.force("ceiling_move")
    assert pet.action == "ceiling_move" and pet._body.y == pet._bounds.top


def test_force_fall_drops_from_the_top_and_lands(pet):
    from phoebe_pet.pet import Mode

    pet.force("fall")
    assert pet.mode is Mode.AIR and pet._body.y == pet._bounds.top
    seen = set()
    for _ in range(600):
        pet.tick(0.016, (9000, 9000))
        seen.add(pet.action)
    assert {"fall", "land"} <= seen and pet.mode is Mode.AUTO


def test_force_previews_a_special_then_goes_back_to_normal(pet):
    from phoebe_pet.pet import PREVIEW_TIME, Mode

    pet.force("talk")
    assert pet.mode is Mode.PREVIEW
    view = pet.tick(0.016, (9000, 9000))
    assert view.frame in pet._actions["talk"].frames
    for _ in range(int(PREVIEW_TIME / 0.016) + 5):
        pet.tick(0.016, (9000, 9000))
    assert (pet.mode, pet.action) == (Mode.AUTO, "stand")


def test_force_rejects_unknown_names_and_lists_known_ones(pet):
    import pytest

    with pytest.raises(ValueError, match="nope"):
        pet.force("nope")
    assert {"walk", "wall_climb", "talk", "fall"} <= set(pet.action_names())


def test_chat_takes_over_a_preview(pet):
    from phoebe_pet.pet import Mode

    pet.force("resist")
    pet.begin_think()
    assert pet.mode is Mode.THINK


INTRO = """
[action.stand]
surface = "floor"
frames = ["shime1"]
frame_ms = 100
speed = 0
duration = [1, 1]
weight = 1
idle_weight = 1
next = ["turn"]

[action.turn]
surface = "floor"
frames = ["t1", "t2", "t3", "t4"]
frame_ms = 100
speed = 0
duration = [0.4, 0.4]
weight = 1
idle_weight = 1
next = ["walk"]
intro = true

[action.walk]
surface = "floor"
frames = ["w1", "w2"]
frame_ms = 100
speed = 60
duration = [1, 1]
weight = 1
idle_weight = 1
next = ["stand"]
"""


@pytest.mark.parametrize("seed", range(30))
def test_intro_picks_the_direction_and_the_next_action_keeps_it(seed, tmp_path):
    path = tmp_path / "actions.toml"
    path.write_text(INTRO, encoding="utf-8")
    actions = load_actions(path)
    rng = random.Random(seed)
    pet = Pet(actions, Chooser(actions, rng), B, (128, 128), rng)
    pet._body.x = B.right - 128  # at the right edge the only way to walk is left
    pet._facing_right = True
    pet._start("turn")
    assert pet._facing_right is False
    pet._body.x = 900
    turning = pet._facing_right
    for _ in range(30):
        pet._facing_right = turning
        pet._start("turn")
        turning = pet._facing_right
        pet._start("walk")
        assert pet._facing_right is turning


def test_fast_animation_is_not_resting_even_when_standing_still(tmp_path):
    """A still pose may be redrawn lazily; a 62 ms animation played in place may not, or it stutters."""
    path = tmp_path / "actions.toml"
    path.write_text(INTRO.replace('frames = ["shime1"]\nframe_ms = 100', 'frames = ["i1", "i2", "i3"]\nframe_ms = 62'), encoding="utf-8")
    quick = load_actions(path)
    rng = random.Random(0)
    pet = Pet(quick, Chooser(quick, rng), B, (128, 128), rng)
    assert pet.action == "stand" and pet.tick(0.0, FAR).resting is False
    assert make().tick(0.0, FAR).resting is True  # the default stand is one 500 ms picture


def test_climbing_down_a_wall_plays_the_climb_backwards():
    def frames(direction):
        pet = make()
        pet._place_on_wall(left=True, y=500)
        pet._start("wall_climb")
        pet._climb_dir = direction
        return [pet.tick(0.05, FAR).frame for _ in range(30)]

    up, down = frames(-1), frames(1)
    order = list(ACTIONS["wall_climb"].frames)
    assert up[0] == order[0] and down[0] == order[-1]
    assert [f for i, f in enumerate(down) if i % 5 == 0] == order[::-1]


def run_until(pet, cond, cap=2000):
    for _ in range(cap):
        if cond():
            break
        pet.tick(0.016, (9000, 9000))
    assert cond()


def test_choose_receives_mood_name(pet, monkeypatch):
    seen = []
    monkeypatch.setattr(pet._chooser, "choose", lambda cur, idle, mood="calm": seen.append(mood) or "stand")
    pet.mood.forced = "sleepy"
    pet._duration = 0
    pet.tick(0.016, (9000, 9000))
    assert seen == ["sleepy"]


def test_hard_throw_queues_thrown_on_landing_and_lowers_cheer(pet):
    before = pet.mood.cheer
    pet.grab((500, 300))
    pet.drag_to((500, 300), 0.05)
    pet.drag_to((1100, 300), 0.05)
    pet.release()
    assert pet.mood.cheer < before and pet.take_events() == []
    run_until(pet, lambda: pet.mode is Mode.AUTO)
    assert pet.take_events() == ["thrown"] and pet.take_events() == []


def test_release_after_struggling_queues_released(pet):
    pet.grab((500, 300))
    for _ in range(80):
        pet.drag_to((500, 300), 0.016)
    pet.release()
    run_until(pet, lambda: pet.mode is Mode.AUTO)
    assert "released" in pet.take_events()


def test_wake_up_queues_woke(qapp):
    # assets/phoebe is not in git; load the repo actions.toml and add a copy of "stand" named "wake_up"
    actions = load_actions(ROOT / "actions.toml")
    actions["wake_up"] = dataclasses.replace(actions["stand"], name="wake_up")
    rng = random.Random(0)
    p = Pet(actions, Chooser(actions, rng), Bounds(0, 0, 1920, 1040), (128, 128), rng)
    p._start("wake_up")
    assert p.take_events() == ["woke"]


def test_mouse_near(pet):
    pet.tick(0.016, (9000, 9000))
    assert not pet.mouse_near
    cx = pet._body.x + 64
    cy = pet._body.y + 64
    pet.tick(0.016, (int(cx), int(cy)))
    assert pet.mouse_near


def test_speaking_shows_talk_only_while_standing(pet):
    pet.force("stand")
    pet.speaking = True
    assert pet.tick(0.016, (9000, 9000)).frame in pet._actions["talk"].frames
    assert pet.mode is Mode.AUTO and pet.action == "stand"
    pet.force("sit")
    assert pet.tick(0.016, (9000, 9000)).frame not in pet._actions["talk"].frames
