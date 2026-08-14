def test_sid_resolution_standard():
    assert resolve_sid(1, CffIndex([])) == "space"
    assert resolve_sid(228, CffIndex([])) == "zcaron"
    assert resolve_sid(390, CffIndex([])) == "Semibold"