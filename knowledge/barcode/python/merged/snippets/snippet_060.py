def test_code39_parser_rejects_unsupported_capabilities(
    options: Code39Options,
    message_fragment: str,
) -> None:
    """GS1 and ECI requests should fail as typed capability errors."""
    with pytest.raises(UnsupportedCapabilityError, match=message_fragment):
        _base_parser().parse("ABC", options=options)