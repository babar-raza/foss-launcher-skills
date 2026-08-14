def test_code39_encoder_matches_golden_modules(vector: Code39Vector) -> None:
    """Code 39 encoding should match a known-good module sequence."""
    symbol = Code39Encoder().encode(_build_payload(vector))
    actual_rows = tuple("".join(str(module) for module in row) for row in symbol.matrix.modules)

    assert actual_rows == vector.expected_modules
    assert symbol.matrix.height == 1