def test_code39_parser_rejects_bytes_input() -> None:
    """Bytes input should fail as an unsupported capability rather than silently decode."""
    with pytest.raises(UnsupportedCapabilityError, match="bytes"):
        _base_parser().parse(b"ABC")