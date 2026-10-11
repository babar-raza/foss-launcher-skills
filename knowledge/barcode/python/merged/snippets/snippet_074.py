def test_ean13_parser_accepts_encode_options_base_type() -> None:
    """EncodeOptions (base type) should be accepted and coerced to Ean13Options defaults."""
    payload = Ean13InputParser().parse("400638133393", options=EncodeOptions())

    assert payload.data == "4006381333931"