def test_ean13_parser_rejects_unsupported_capabilities(
    options: Ean13Options | EncodeOptions,
    message_fragment: str,
) -> None:
    """Requesting unsupported capabilities should raise a typed capability error."""
    with pytest.raises(UnsupportedCapabilityError, match=message_fragment):
        Ean13InputParser().parse("400638133393", options=options)