def test_build_line_converts_to_local_coordinates():
    # Rect origin (100,100); L is absolute -> local subtracts the origin.
    gen = build_appearance("Line", (100, 100, 300, 300), {"L": [120, 120, 220, 180]})
    assert gen is not None
    assert b"20 20 m" in gen.content
    assert b"120 80 l" in gen.content
    assert b"\nS\n" in gen.content