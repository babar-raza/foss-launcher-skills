def test_solid_border_emits_no_dash():
    gen = build_appearance("Square", _RECT, {"C": [0, 0, 0], "BS": {"W": 1}})
    assert b" d\n" not in gen.content