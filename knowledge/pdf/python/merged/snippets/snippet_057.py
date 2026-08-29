def test_dash_from_legacy_border_array():
    gen = build_appearance(
        "Circle", _RECT, {"C": [0, 0, 0], "Border": [0, 0, 1, [2, 2]]}
    )
    assert b"[2 2] 0 d" in gen.content