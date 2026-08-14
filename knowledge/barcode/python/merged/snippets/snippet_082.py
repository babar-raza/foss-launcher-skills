def test_ean13_parser_rejects_wrong_length() -> None:
    """10-digit input is neither the 12-digit nor the 13-digit accepted form."""
    with pytest.raises(InvalidInputError, match="12 or 13 digits"):
        Ean13InputParser().parse("4006381333")