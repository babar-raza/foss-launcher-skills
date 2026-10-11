def test_code39_parser_rejects_empty_text() -> None:
    """Code 39 requires at least one supported text character."""
    with pytest.raises(InvalidInputError, match="empty"):
        _base_parser().parse("")