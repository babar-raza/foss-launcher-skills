def test_build_polyline_is_open_and_stroke_only():
    gen = build_appearance(
        "PolyLine", (0, 0, 100, 100), {"Vertices": [0, 0, 50, 50, 100, 0]}
    )
    assert gen is not None
    assert b"\nh\n" not in gen.content
    assert b"\nS\n" in gen.content