def test_code39_parser_preserves_whitespace_verbatim() -> None:
    """Supported spaces should survive parsing without trimming or rewriting."""
    data = "A B C"

    payload = _base_parser().parse(data)

    assert payload.data == data