def test_ean13_parser_rejects_various_wrong_lengths(length: int) -> None:
    """Any digit-only string that is neither 12 nor 13 characters must be rejected."""
    data = "1" * length
    with pytest.raises(InvalidInputError, match="12 or 13 digits"):
        Ean13InputParser().parse(data)