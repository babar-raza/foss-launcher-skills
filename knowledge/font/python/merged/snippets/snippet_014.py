def test_cff_charstring_zero_is_bytes(opensans_cff):
    assert isinstance(opensans_cff.charstrings[0], bytes)