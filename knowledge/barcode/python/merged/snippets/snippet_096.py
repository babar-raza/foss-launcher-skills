def test_ean8_parser_accepts_encode_options_base_type() -> None:
    """The base EncodeOptions type is accepted and coerced."""
    payload = Ean8InputParser().parse("5512345", options=EncodeOptions())
    assert payload.data == "55123457"