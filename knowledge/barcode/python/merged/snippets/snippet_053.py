def test_code39_parser_option_override_enables_full_ascii_on_base_definition() -> None:
    """An explicit full_ascii=True should flip a base definition into Full-ASCII mode."""
    payload = _base_parser().parse("abc", options=Code39Options(full_ascii=True))

    assert payload.code39_encode_mode is Code39EncodeMode.FULL_ASCII