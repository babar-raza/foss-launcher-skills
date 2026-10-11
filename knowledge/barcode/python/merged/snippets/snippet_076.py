def test_ean13_parser_rejects_non_string_input() -> None:
    """Only text strings are valid; other types must be rejected with a clear error."""
    with pytest.raises(InvalidInputError, match="text string"):
        Ean13InputParser().parse(400638133393)  # type: ignore[arg-type]