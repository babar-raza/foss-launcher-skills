def test_cff_standard_strings() -> None:
    strings = cff_standard_strings()
    assert len(strings) == 391
    assert strings[0] == ".notdef"
    assert strings[1] == "space"