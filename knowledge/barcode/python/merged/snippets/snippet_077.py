def test_ean13_parser_rejects_empty_string() -> None:
    """An empty (or whitespace-only) string must not reach digit validation."""
    with pytest.raises(InvalidInputError, match="empty"):
        Ean13InputParser().parse("")