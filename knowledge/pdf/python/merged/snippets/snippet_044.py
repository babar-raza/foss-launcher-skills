def test_dash_applies_to_line_and_freetext():
    line = build_appearance(
        "Line", _RECT, {"L": [10, 10, 100, 60], "BS": {"S": N("D"), "D": [4]}}
    )
    assert b"[4] 0 d" in line.content
    ft = build_appearance(
        "FreeText",
        _RECT,
        {"Contents": "hi", "BS": {"S": N("D"), "D": [5, 3], "W": 2}},
    )
    assert b"[5 3] 0 d" in ft.content