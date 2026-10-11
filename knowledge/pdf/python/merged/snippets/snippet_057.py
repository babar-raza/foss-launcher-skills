def test_dash_style_d_without_array_defaults():
    gen = build_appearance(
        "Square", _RECT, {"C": [0, 0, 0], "BS": {"S": N("D"), "W": 1}}
    )
    assert b"[3] 0 d" in gen.content