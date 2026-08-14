def test_code39_parser_carries_check_digit_request() -> None:
    """A check-digit request should propagate onto the normalized payload."""
    payload = _base_parser().parse("ABC", options=Code39Options(add_check_digit=True))

    assert payload.code39_add_check_digit is True