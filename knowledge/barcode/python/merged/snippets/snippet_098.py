def test_ean8_parser_rejects_non_string_input() -> None:
    """Non-string, non-bytes input is rejected as invalid."""
    with pytest.raises(InvalidInputError, match="text string"):
        Ean8InputParser().parse(5512345)  # type: ignore[arg-type]