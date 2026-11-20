import pytest

from phoebe_pet.config import Config, load_config


def write(tmp_path, text):
    p = tmp_path / "c.toml"
    p.write_text(text, encoding="utf-8")
    return p


def test_missing_file_gives_defaults(tmp_path):
    assert load_config(tmp_path / "none.toml") == Config()


def test_values_override_defaults(tmp_path):
    cfg = load_config(write(tmp_path, 'scale = 1.5\nmodel = "x"\n'))
    assert (cfg.scale, cfg.model, cfg.character) == (1.5, "x", "placeholder")


def test_unknown_key_ignored(tmp_path):
    assert load_config(write(tmp_path, "nope = 1\n")) == Config()


def test_wrong_type_names_the_key(tmp_path):
    with pytest.raises(ValueError, match="scale"):
        load_config(write(tmp_path, 'scale = "big"\n'))


def test_scale_out_of_range_rejected(tmp_path):
    with pytest.raises(ValueError, match="scale"):
        load_config(write(tmp_path, "scale = 0\n"))


def test_integer_accepted_for_float_field(tmp_path):
    assert load_config(write(tmp_path, "scale = 2\n")).scale == 2.0


def test_bool_not_accepted_as_number(tmp_path):
    with pytest.raises(ValueError, match="speed"):
        load_config(write(tmp_path, "speed = true\n"))


def test_history_turns_must_be_positive(tmp_path):
    with pytest.raises(ValueError, match="history_turns"):
        load_config(write(tmp_path, "history_turns = 0\n"))
