from phoebe_pet.fullscreen import covers, foreground_is_fullscreen


def test_covers():
    mon = (0, 0, 1920, 1080)
    assert covers((0, 0, 1920, 1080), mon) and covers((-8, -8, 1928, 1088), mon)
    assert not covers((0, 0, 1920, 1040), mon) and not covers((100, 100, 900, 700), mon)


def test_foreground_check_runs_without_error():
    assert foreground_is_fullscreen() in (True, False)
