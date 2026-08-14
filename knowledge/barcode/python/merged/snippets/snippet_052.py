def test_code39_parser_uses_definition_full_ascii_default() -> None:
    """The code39ext definition should default lowercase input to Full-ASCII mode."""
    payload = _ext_parser().parse("abc")

    assert payload.symbology == "code39ext"
    assert payload.code39_encode_mode is Code39EncodeMode.FULL_ASCII