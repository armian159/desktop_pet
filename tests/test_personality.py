import re

from pathlib import Path

import pytest

from phoebe_pet.mood import NAMES
from phoebe_pet.personality import LINE_KEYS, Personality, load_personality, personality_file

ROOT = Path(__file__).resolve().parent.parent


def write(tmp_path, text):
    path = tmp_path / "personality.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_repo_file_loads_with_lines_for_every_key():
    p = load_personality(ROOT / "personality.toml")
    assert set(LINE_KEYS) <= set(p.lines) and all(p.lines[k] for k in LINE_KEYS)
    assert p.affinity["lie"]["sleepy"] > 1


def test_repo_lines_are_short_and_plain():
    p = load_personality(ROOT / "personality.toml")
    for key, lines in p.lines.items():
        for line in lines:
            assert len(line) < 40, (key, line)
            assert line.count("방랑자님") <= 1, (key, line)
            assert re.search(r"요[.!?…~]*$", line), (key, line)
            assert not re.search(r"(^|\s)(어|저|꺄), (어|저)", line), (key, line)


def test_missing_file_is_empty(tmp_path):
    assert load_personality(tmp_path / "none.toml") == Personality({}, {})


def test_unknown_mood_name_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="'lie'.*'dreamy'"):
        load_personality(write(tmp_path, "[affinity.lie]\ndreamy = 2"))


def test_negative_factor_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="negative"):
        load_personality(write(tmp_path, "[affinity.lie]\nsleepy = -1"))


def test_lines_must_be_lists_of_text(tmp_path):
    with pytest.raises(ValueError, match="lines"):
        load_personality(write(tmp_path, '[lines]\nsleepy = "하암"'))


def test_character_folder_overrides(tmp_path):
    (tmp_path / "assets" / "fancy").mkdir(parents=True)
    own = tmp_path / "assets" / "fancy" / "personality.toml"
    own.write_text("", encoding="utf-8")
    assert personality_file(tmp_path, "fancy") == own
    assert personality_file(tmp_path, "plain") == tmp_path / "personality.toml"


@pytest.mark.parametrize("value", ["inf", "nan", "-inf"])
def test_non_finite_factor_is_an_error(tmp_path, value):
    with pytest.raises(ValueError, match="finite"):
        load_personality(write(tmp_path, f"[affinity.walk]\nhappy = {value}\n"))


def test_repo_file_maps_gestures_for_ten_keys():
    p = load_personality(ROOT / "personality.toml")
    assert set(p.gestures) == set(LINE_KEYS) - {"woke"}
    assert all(v == f"gesture_{k}" for k, v in p.gestures.items())


def test_unknown_gesture_key_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="gestures.*'dance'"):
        load_personality(write(tmp_path, '[gestures]\ndance = "gesture_dance"'))


def test_gesture_value_must_be_text(tmp_path):
    with pytest.raises(ValueError, match="gestures"):
        load_personality(write(tmp_path, "[gestures]\nsleepy = 3"))


def test_every_line_list_has_eight_lines():
    p = load_personality(ROOT / "personality.toml")
    assert all(len(p.lines[k]) == 8 for k in LINE_KEYS)


def test_mood_gestures_only_in_their_own_mood():
    p = load_personality(ROOT / "personality.toml")
    for mood in NAMES:
        factors = p.affinity[f"gesture_{mood}"]
        assert factors[mood] == 1 and all(factors[m] == 0 for m in NAMES if m != mood)
