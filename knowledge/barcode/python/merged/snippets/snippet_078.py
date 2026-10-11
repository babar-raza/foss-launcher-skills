def test_ean13_parser_rejects_whitespace_only_string() -> None:
    """Whitespace stripped to nothing is indistinguishable from an empty payload."""
    with pytest.raises(InvalidInputError, match="empty"):
        Ean13InputParser().parse(" ")