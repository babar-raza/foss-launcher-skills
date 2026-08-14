def test_code39_parser_rejects_unsupported_option_containers(options: object) -> None:
    """Only the documented option container types should be accepted."""
    with pytest.raises(InvalidInputError, match="encode options"):
        _base_parser().parse("ABC", options=options)  # type: ignore[arg-type]