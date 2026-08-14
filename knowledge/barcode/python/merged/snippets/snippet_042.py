def test_code128_parser_rejects_unsupported_capabilities(
    options: Code128Options | EncodeOptions,
    message_fragment: str,
) -> None:
    """Unsupported capabilities should fail as typed capability errors."""
    with pytest.raises(UnsupportedCapabilityError, match=message_fragment):
        Code128InputParser().parse("ABC123", options=options)