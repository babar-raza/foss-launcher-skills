def test_ean8_parser_rejects_whitespace_only_string() -> None:
    """A whitespace-only string is treated as empty and rejected."""
    with pytest.raises(InvalidInputError, match="empty"):
        Ean8InputParser().parse(" ")