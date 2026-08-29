def test_build_polygon_closes_and_fills():
    gen = build_appearance(
        "Polygon",
        (0, 0, 100, 100),
        {"Vertices": [0, 0, 100, 0, 50, 100], "IC": [0, 0, 1]},
    )
    assert gen is not None
    assert b"0 0 m" in gen.content
    assert b"\nh\n" in gen.content  # closed
    assert b"\nB\n" in gen.content  # fill + stroke