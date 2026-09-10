def test_polyline_endings_orient_to_end_edges():
    gen = build_appearance(
        "PolyLine",
        _RECT,
        {"Vertices": [10, 10, 60, 60, 110, 10], "LE": [N("OpenArrow"), N("OpenArrow")]},
    )
    assert gen is not None
    # Shaft stroke plus one stroke per open-arrow head.
    assert gen.content.count(b"\nS\n") == 3