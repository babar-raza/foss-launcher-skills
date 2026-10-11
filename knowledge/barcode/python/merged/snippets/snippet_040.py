def test_code128_parser_preserves_supported_whitespace_verbatim() -> None:
    """Supported spaces should survive parsing without trimming or rewriting."""
    data = " A B "

    payload = Code128InputParser().parse(data)

    assert payload.data == data