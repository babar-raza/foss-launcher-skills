def test_ean8_parser_rejects_empty_string() -> None:
    """An empty string is rejected."""
    with pytest.raises(InvalidInputError, match="empty"):
        Ean8InputParser().parse("")