def test_code39_parser_defaults_check_digit_to_false() -> None:
    """Without an explicit request the payload should report no check digit."""
    payload = _base_parser().parse("ABC")

    assert payload.code39_add_check_digit is False