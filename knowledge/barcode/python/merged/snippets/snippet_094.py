def test_ean8_parser_computes_check_digit_for_second_value() -> None:
    """A second 7-digit value confirms the check digit is computed, not hard-coded."""
    payload = Ean8InputParser().parse("1234567")
    assert payload.data == "12345670"