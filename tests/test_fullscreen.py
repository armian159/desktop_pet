from phoebe_pet.fullscreen import WS_CAPTION, covers, foreground_is_fullscreen, is_fullscreen


def test_covers():
    mon = (0, 0, 1920, 1080)
    assert covers((0, 0, 1920, 1080), mon) and covers((-8, -8, 1928, 1088), mon)
    assert not covers((0, 0, 1920, 1040), mon) and not covers((100, 100, 900, 700), mon)


def test_foreground_check_runs_without_error():
    assert foreground_is_fullscreen() in (True, False)


MON = (0, 0, 1920, 1080)


def test_borderless_window_covering_the_monitor_is_fullscreen():
    assert is_fullscreen((0, 0, 1920, 1080), MON, style=0)


def test_maximized_titled_window_is_not_fullscreen_even_with_hidden_taskbar():
    # With the taskbar on auto-hide a maximized window overhangs the whole monitor.
    assert not is_fullscreen((-8, -8, 1928, 1088), MON, style=WS_CAPTION)


def test_small_borderless_window_is_not_fullscreen():
    assert not is_fullscreen((100, 100, 900, 700), MON, style=0)
