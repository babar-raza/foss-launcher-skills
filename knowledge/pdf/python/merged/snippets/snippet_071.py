def test_build_caret_honours_rgb_colour():
    gen = build_appearance("Caret", (0, 0, 20, 20), {"C": [1, 0, 0]})
    assert gen is not None
    assert b"1 0 0 rg" in gen.content