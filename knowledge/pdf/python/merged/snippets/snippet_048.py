def test_line_none_ending_draws_only_the_shaft():
    gen = build_appearance(
        "Line", _RECT, {"L": [10, 40, 100, 40], "LE": [N("None"), N("None")]}
    )
    assert gen.content.count(b"\nS\n") == 1  # shaft only