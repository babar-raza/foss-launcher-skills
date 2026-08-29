def test_build_caret_draws_filled_triangle():
    gen = build_appearance("Caret", (0, 0, 20, 20), {})
    assert gen is not None
    assert b"0 g" in gen.content  # defaults to black
    assert gen.content.count(b" l\n") == 2  # two edges of the triangle
    assert b"\nh\n" in gen.content and b"\nf\n" in gen.content
    assert gen.fonts == {}  # marker shape needs no font