def test_line_diamond_and_circle_endings():
    diamond = build_appearance(
        "Line", _RECT, {"L": [10, 40, 100, 40], "LE": [N("Diamond"), N("None")]}
    )
    assert b"\nb\n" in diamond.content
    circle = build_appearance(
        "Line", _RECT, {"L": [10, 40, 100, 40], "LE": [N("None"), N("Circle")]}
    )
    assert circle.content.count(b" c") == 4  # four Bézier arcs