def test_dash_from_border_style_array():
    gen = build_appearance(
        "Square", _RECT, {"C": [0, 0, 0], "BS": {"S": N("D"), "D": [3, 2], "W": 2}}
    )
    assert gen is not None
    assert b"[3 2] 0 d" in gen.content