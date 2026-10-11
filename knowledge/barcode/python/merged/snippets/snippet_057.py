def test_code39_parser_accepts_plain_encode_options_container() -> None:
    """A plain EncodeOptions container should resolve to the definition's default mode."""
    payload = _base_parser().parse("ABC", options=EncodeOptions())

    assert payload.code39_encode_mode is Code39EncodeMode.BASE
    assert payload.code39_add_check_digit is False