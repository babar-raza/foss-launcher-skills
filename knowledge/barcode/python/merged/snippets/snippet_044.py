def test_code128_parser_rejects_text_that_conflicts_with_the_requested_mode(
    data: str,
    options: Code128Options | None,
    message_fragment: str,
) -> None:
    """Standard-invalid text should fail before the encoder runs."""
    with pytest.raises(InvalidInputError, match=message_fragment):
        Code128InputParser().parse(data, options=options)