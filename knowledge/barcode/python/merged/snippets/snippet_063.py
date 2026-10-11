def test_code39_parser_accepts_star_in_full_ascii_mode() -> None:
    """The '*' character is only forbidden in base mode; Full-ASCII should accept it."""
    payload = _ext_parser().parse("*")

    assert payload.code39_encode_mode is Code39EncodeMode.FULL_ASCII
    assert payload.data == "*"