def test_build_missing_geometry_returns_none():
    assert build_appearance("Line", (0, 0, 100, 100), {}) is None
    assert build_appearance("Ink", (0, 0, 100, 100), {}) is None
    assert build_appearance("Highlight", (0, 0, 100, 100), {}) is None