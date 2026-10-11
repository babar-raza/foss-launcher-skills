def test_ean13_parser_rejects_non_ascii_digits() -> None:
    """Unicode decimal digits are not valid EAN-13 input characters."""
    with pytest.raises(InvalidInputError, match="position 12"):
        Ean13InputParser().parse("40063813339\u0663")