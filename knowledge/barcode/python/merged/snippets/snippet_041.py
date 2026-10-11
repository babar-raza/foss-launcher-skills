def test_code128_parser_preserves_supported_typed_encode_modes(
    data: str,
    mode: Code128EncodeMode,
) -> None:
    """Parser output should carry the exact typed encode mode through to encoding."""
    payload = Code128InputParser().parse(data, options=Code128Options(encode_mode=mode))

    assert payload.code128_encode_mode is mode