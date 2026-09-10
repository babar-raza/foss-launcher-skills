def test_macexpert_encoding_table() -> None:
    mac_expert = base_encoding_table("MacExpertEncoding")
    assert mac_expert is not None and len(mac_expert) == 256
    assert mac_expert[0x21] == "exclamsmall"
    assert mac_expert[0x30] == "zerooldstyle"
    assert mac_expert[0x41] == ""  # undefined -- *not* Latin "A"
    # Every name it defines belongs to the Adobe Expert glyph repertoire, and
    # resolves to a scalar, so an Expert-encoded font can also extract as text.
    expert = set(cff_predefined_charset(1))
    defined = [name for name in mac_expert if name]
    assert len(defined) == 165
    assert all(name in expert for name in defined)
    assert all(glyph_name_to_unicode(name) is not None for name in defined)