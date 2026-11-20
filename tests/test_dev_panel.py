import pytest

from phoebe_pet.dev_panel import DevPanel
from phoebe_pet.pet import PREVIEW_TIME, Mode


@pytest.fixture
def panel(qapp, pet):
    p = DevPanel(pet)
    yield p
    p.timer.stop()
    p.close()


def run(pet, seconds):
    for _ in range(int(seconds / 0.016)):
        pet.tick(0.016, (9000, 9000))


def test_there_is_a_button_for_every_action(panel, pet):
    assert set(panel.buttons) == set(pet.action_names())


def test_clicking_a_button_makes_the_pet_do_it(panel, pet):
    panel.buttons["wall_climb"].click()
    assert pet.action == "wall_climb"
    panel.buttons["talk"].click()
    assert pet.mode is Mode.PREVIEW and pet.action == "talk"


def test_status_shows_what_the_pet_is_doing(panel, pet):
    panel.buttons["sit"].click()
    pet.tick(0.016, (9000, 9000))
    panel.refresh()
    assert "sit" in panel.status.text() and "auto" in panel.status.text()


def test_without_repeat_the_pet_moves_on(panel, pet):
    panel.buttons["talk"].click()
    run(pet, PREVIEW_TIME + 0.5)
    panel.refresh()
    assert pet.action != "talk"


def test_repeat_keeps_the_chosen_action_going(panel, pet):
    panel.repeat.setChecked(True)
    panel.buttons["talk"].click()
    run(pet, PREVIEW_TIME + 0.5)
    panel.refresh()
    assert pet.action == "talk"
    panel.buttons["walk"].click()
    for _ in range(40):
        run(pet, 1.0)
        panel.refresh()
        assert pet.action in ("walk", "wall_hold") or pet.mode is Mode.AUTO
    assert pet.action == "walk"


def test_repeat_leaves_a_fall_alone_until_it_has_landed(panel, pet):
    panel.repeat.setChecked(True)
    panel.buttons["fall"].click()
    seen = set()
    for _ in range(200):
        pet.tick(0.016, (9000, 9000))
        panel.refresh()
        seen.add(pet.action)
    assert "land" in seen


def test_repeat_does_not_fight_a_drag(panel, pet):
    panel.repeat.setChecked(True)
    panel.buttons["sit"].click()
    pet.grab((500, 500))
    panel.refresh()
    assert pet.mode is Mode.DRAGGED


def test_status_shows_mood(panel, pet):
    pet.mood.energy = 0.62
    panel.refresh()
    assert "기운 0.62" in panel.status.text() and "[calm]" in panel.status.text()


def test_mood_button_cycles_forced_names(panel, pet):
    seen = []
    for _ in range(6):
        panel.mood_button.click()
        seen.append(pet.mood.forced)
    assert seen == ["sleepy", "sulky", "bored", "happy", "calm", None]


def test_speak_button_calls_back(qapp, pet):
    calls = []
    p = DevPanel(pet, speak_now=lambda: calls.append(1))
    p.speak_button.click()
    assert calls == [1]
    p.timer.stop()
    p.close()


def test_speak_button_disabled_without_callback(panel):
    assert not panel.speak_button.isEnabled()


def test_status_shows_time_until_next_speech(qapp, pet):
    p = DevPanel(pet, next_speech=lambda: 192.0)
    assert "다음 혼잣말 3분 12초" in p.status.text()
    p.timer.stop()
    p.close()


def test_status_without_next_speech_shows_dash(panel):
    assert "다음 혼잣말 —" in panel.status.text()
