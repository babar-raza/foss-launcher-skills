def test_base_encoding_tables() -> None:
    standard = base_encoding_table("StandardEncoding")
    win = base_encoding_table("WinAnsiEncoding")
    mac = base_encoding_table("MacRomanEncoding")
    assert standard is not None and len(standard) == 256
    assert standard[65] == "A"
    assert win[0x80] == "Euro" and win[0xA0] == "space" and win[0x95] == "bullet"
    assert win[0x81] == ""  # undefined WinAnsi code
    assert mac[65] == "A"
    # PDF 32000-1 Table 114 allows exactly four names; anything else is malformed.
    assert base_encoding_table("ExpertEncoding") is None  # a Type 1 name, not PDF's
    assert base_encoding_table("bogus") is None