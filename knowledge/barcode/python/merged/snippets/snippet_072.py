def test_ean13_parser_accepts_second_known_12_digit_value() -> None:
    """A second known barcode verifies that check digit computation is not hard-coded."""
    payload = Ean13InputParser().parse("590123412345")

    assert payload == NormalizedPayload(symbology="ean13", data="5901234123457", input_kind="text")