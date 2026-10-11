def test_square_without_be_stays_rectangular():
    gen = build_appearance("Square", _RECT, {"C": [0, 0, 0], "BS": {"W": 1}})
    assert b" re" in gen.content
    assert b" c\n" not in gen.content