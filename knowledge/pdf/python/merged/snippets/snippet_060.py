def test_line_closed_arrow_is_filled():
    gen = build_appearance(
        "Line",
        _RECT,
        {"L": [10, 40, 100, 40], "C": [1, 0, 0], "LE": [N("None"), N("ClosedArrow")]},
    )
    assert b"\nb\n" in gen.content  # closepath-fill-stroke triangle
    assert b"1 0 0 rg" in gen.content  # filled with the line colour