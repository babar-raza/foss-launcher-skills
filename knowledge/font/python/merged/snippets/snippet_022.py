def test_sid_resolution_custom():
    idx = CffIndex([b"custom-name"])
    assert resolve_sid(391, idx) == "custom-name"