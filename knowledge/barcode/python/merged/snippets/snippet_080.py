def test_ean13_parser_rejects_non_digit_characters_at_first_position() -> None:
    """A non-digit at position 1 should be reported correctly."""
    with pytest.raises(InvalidInputError, match="position 1"):
        Ean13InputParser().parse("X00638133393")