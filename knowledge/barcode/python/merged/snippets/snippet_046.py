def test_code128_parser_rejects_non_enum_encode_modes(options: Code128Options) -> None:
    """encode_mode must be expressed through the shared Code128 enum."""
    with pytest.raises(InvalidInputError, match="Code128EncodeMode"):
        Code128InputParser().parse("ABC123", options=options)