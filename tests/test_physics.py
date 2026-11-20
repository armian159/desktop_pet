import pytest

from phoebe_pet.physics import Body, Bounds, Contact, clamp, on_floor, step_air

B = Bounds(0, 0, 1920, 1040)


def body(**kw):
    return Body(**{"x": 900, "y": 100, "vx": 0, "vy": 0, "w": 128, "h": 128, **kw})


def test_falls_and_lands_exactly_on_floor():
    b = body()
    contacts = [step_air(b, B, 1 / 60) for _ in range(600)]
    assert Contact.FLOOR in contacts and b.y == 1040 - 128 and b.vy == 0


def test_gravity_accelerates():
    b = body()
    step_air(b, B, 0.01)
    assert b.vy == pytest.approx(24.0)


def test_thrown_left_hits_left_wall():
    b = body(x=50, vx=-2000, vy=-500)
    assert step_air(b, B, 0.05) == Contact.LEFT_WALL and b.x == 0 and b.vx == 0


def test_thrown_right_hits_right_wall():
    b = body(x=1750, vx=2000, vy=-500)
    assert step_air(b, B, 0.05) == Contact.RIGHT_WALL and b.x == 1920 - 128 and b.vx == 0


def test_thrown_up_hits_ceiling():
    b = body(y=10, vy=-2000)
    assert step_air(b, B, 0.05) == Contact.CEILING and b.y == 0


def test_free_flight_reports_no_contact():
    assert step_air(body(), B, 1 / 60) == Contact.NONE


def test_huge_velocity_and_dt_stay_inside():
    b = body(vx=1e9, vy=-1e9)
    for _ in range(100):
        step_air(b, B, 30.0)
    assert 0 <= b.x <= 1920 - 128 and 0 <= b.y <= 1040 - 128


def test_clamp_pulls_body_inside_smaller_bounds():
    b = body(x=1800, y=1000)
    clamp(b, Bounds(0, 0, 1280, 680))
    assert (b.x, b.y) == (1280 - 128, 680 - 128)


def test_bounds_smaller_than_body_do_not_crash():
    b = body()
    clamp(b, Bounds(0, 0, 50, 50))
    assert (b.x, b.y) == (0, 0)


def test_on_floor():
    assert on_floor(body(y=1040 - 128), B) and not on_floor(body(), B)


def test_offset_bounds_respected():
    bounds = Bounds(100, 50, 900, 700)
    b = body(x=0, y=0)
    clamp(b, bounds)
    assert (b.x, b.y) == (100, 50)
