def test_ean8_parser_computes_check_digit_from_7_digit_input() -> None:
    """A 7-digit value gets its check digit computed and appended."""
    payload = Ean8InputParser().parse("5512345")
    assert payload == NormalizedPayload(symbology="ean8", data="55123457", input_kind="text")