def test_line_open_arrow_end_adds_strokes():
    plain = build_appearance("Line", _RECT, {"L": [10, 40, 100, 40], "C": [0, 0, 0]})
    arrow = build_appearance(
        "Line",
        _RECT,
        {"L": [10, 40, 100, 40], "C": [0, 0, 0], "LE": [N("None"), N("OpenArrow")]},
    )
    # The arrowhead adds two more line segments and a stroke beyond the shaft.
    assert arrow.content.count(b" l") > plain.content.count(b" l")
    assert arrow.content.count(b"\nS\n") == 2  # shaft + arrowhead