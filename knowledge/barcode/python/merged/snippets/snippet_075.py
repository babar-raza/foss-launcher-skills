def test_ean13_parser_rejects_bytes_input() -> None:
    """EAN-13 is a digit-only symbology and must not silently coerce bytes."""
    with pytest.raises(UnsupportedCapabilityError, match="bytes"):
        Ean13InputParser().parse(b"400638133393")  # type: ignore[arg-type]