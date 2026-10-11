def test_ean13_parser_accepts_13_digit_input_when_flag_is_set() -> None:
    """13-digit input with a correct check digit should succeed when the flag is enabled."""
    payload = Ean13InputParser().parse(
        "4006381333931",
        options=Ean13Options(allow_check_digit_input=True),
    )

    assert payload == NormalizedPayload(symbology="ean13", data="4006381333931", input_kind="text")