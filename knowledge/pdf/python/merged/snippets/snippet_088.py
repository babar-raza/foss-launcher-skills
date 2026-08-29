def test_build_degenerate_rect_returns_none():
    assert build_appearance("Square", (0, 0, 0, 100), {"C": [0]}) is None