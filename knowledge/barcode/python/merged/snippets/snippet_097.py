def test_ean8_parser_rejects_bytes_input() -> None:
    """Bytes input is unsupported for EAN-8."""
    with pytest.raises(UnsupportedCapabilityError, match="bytes"):
        Ean8InputParser().parse(b"5512345")  # type: ignore[arg-type]