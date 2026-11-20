from phoebe_pet.frames import resolve

ALL_USED = {f"shime{i}" for i in range(1, 34)} | {"talk1", "talk2", "think1", "think2"}


def test_present_frame_resolves_to_itself():
    assert resolve("shime4", {"shime1", "shime4"}) == "shime4"


def test_single_frame_set_resolves_everything():
    assert {resolve(n, {"shime1"}) for n in ALL_USED} == {"shime1"}


def test_talk_falls_back_to_stand_and_think_to_sit():
    have = {"shime1", "shime11"}
    assert resolve("talk1", have) == "shime1"
    assert resolve("think1", have) == "shime11"


def test_fallback_prefers_same_motion_family():
    assert resolve("shime12", {"shime1", "shime13"}) == "shime13"
    assert resolve("shime24", {"shime1", "shime23"}) == "shime23"


def test_unknown_name_falls_back_to_stand():
    assert resolve("whatever", {"shime1"}) == "shime1"
