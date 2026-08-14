def test_code128_encoder_matches_golden_modules() -> None:
    """Code 128 encoding should match a known-good module sequence."""
    symbol = Code128Encoder().encode(_build_payload(CODE128_A.input_data))
    actual_rows = tuple("".join(str(module) for module in row) for row in symbol.matrix.modules)

    assert actual_rows == CODE128_A.expected_modules
    assert symbol.metadata.display_text == CODE128_A.input_data
    assert symbol.matrix.height == 1