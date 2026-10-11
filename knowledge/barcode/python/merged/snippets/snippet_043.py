def test_code128_parser_rejects_empty_text() -> None:
    """Code 128 requires at least one supported text character."""
    with pytest.raises(InvalidInputError, match="empty"):
        Code128InputParser().parse("")