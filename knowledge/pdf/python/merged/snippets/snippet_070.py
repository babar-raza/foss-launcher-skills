def test_build_square_with_stroke_and_fill():
    gen = build_appearance(
        "Square", (0, 0, 100, 100), {"C": [1, 0, 0], "IC": [0, 1, 0], "BS": {"W": 2}}
    )
    assert gen is not None
    assert b"1 0 0 RG" in gen.content  # red stroke
    assert b"0 1 0 rg" in gen.content  # green fill
    assert b"2 w" in gen.content
    assert b" re" in gen.content
    assert b"\nB\n" in gen.content  # fill + stroke
    assert gen.ext_gstates == {}