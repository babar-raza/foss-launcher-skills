def test_code128_parser_accepts_control_characters_in_auto_mode() -> None:
    """AUTO should preserve standard-valid Code Set A control characters."""
    payload = Code128InputParser().parse("A\n")

    assert payload == NormalizedPayload(
        symbology="code128",
        data="A\n",
        input_kind="text",
        code128_encode_mode=Code128EncodeMode.AUTO,
    )