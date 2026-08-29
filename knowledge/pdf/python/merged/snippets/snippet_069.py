def test_build_square_without_colour_defaults_to_black_border():
    gen = build_appearance("Square", (0, 0, 50, 50), {})
    assert gen is not None
    assert b"0 G" in gen.content
    assert b"\nS\n" in gen.content  # stroke only