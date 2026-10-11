def test_square_cloud_border_replaces_rectangle():
    gen = build_appearance(
        "Square", _RECT, {"C": [0, 0, 1], "BE": {"S": N("C"), "I": 2}, "BS": {"W": 1}}
    )
    assert gen is not None
    assert b" c\n" in gen.content  # scalloped Bézier edges
    assert b" re" not in gen.content  # not a plain rectangle