def test_code128_parser_rejects_bytes_input() -> None:
    """The should not silently coerce bytes into text."""
    with pytest.raises(UnsupportedCapabilityError, match="bytes"):
        Code128InputParser().parse(b"ABC123")