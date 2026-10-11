def test_build_unsupported_subtype_returns_none():
    assert build_appearance("Sound", (0, 0, 20, 20), {}) is None
    assert build_appearance("Popup", (0, 0, 20, 20), {}) is None
    assert build_appearance("Widget", (0, 0, 20, 20), {}) is None