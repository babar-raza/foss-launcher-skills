def test_ean13_parser_computes_check_digit_from_12_digit_input() -> None:
    """12-digit input should have its check digit computed and appended automatically."""
    payload = Ean13InputParser().parse("400638133393")

    assert payload == NormalizedPayload(symbology="ean13", data="4006381333931", input_kind="text")