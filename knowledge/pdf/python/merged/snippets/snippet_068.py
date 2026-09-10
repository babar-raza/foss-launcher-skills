def test_polygon_cloud_border():
    gen = build_appearance(
        "Polygon",
        _RECT,
        {"Vertices": [10, 10, 110, 10, 60, 70], "C": [0, 0, 0], "BE": {"S": N("C"), "I": 1}},
    )
    assert gen is not None
    assert b" c\n" in gen.content