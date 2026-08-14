def test_ean13_parser_rejects_unsupported_option_containers(options: object) -> None:
    """Only the documented option container types should be accepted."""
    with pytest.raises(InvalidInputError, match="encode options"):
        Ean13InputParser().parse("400638133393", options=options)  # type: ignore[arg-type]