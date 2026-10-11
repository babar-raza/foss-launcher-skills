def test_code39_parser_accepts_base_text_with_full_payload_equality() -> None:
    """A simple base input should normalize into the exact Code 39 payload contract."""
    payload = _base_parser().parse("CODE 39")

    assert payload == NormalizedPayload(
        symbology="code39",
        data="CODE 39",
        input_kind="text",
        code39_encode_mode=Code39EncodeMode.BASE,
        code39_add_check_digit=False,
    )