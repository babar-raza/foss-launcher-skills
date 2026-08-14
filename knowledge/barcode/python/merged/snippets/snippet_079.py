def test_ean13_parser_rejects_non_digit_characters_and_reports_position() -> None:
    """Non-digit characters must be caught and the 1-based position must appear in the message."""
    with pytest.raises(InvalidInputError, match="position 4"):
        Ean13InputParser().parse("400A38133393")