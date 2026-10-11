def test_code128_parser_rejects_unsupported_option_containers(
    options: object,
) -> None:
    """Only the documented option container types should be accepted."""
    with pytest.raises(InvalidInputError, match="encode options"):
        Code128InputParser().parse("ABC123", options=options)  # type: ignore[arg-type]