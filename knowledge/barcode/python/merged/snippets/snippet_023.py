def test_code128_encoder_matches_additional_code_set_b_golden_modules(
    vector: Code128Vector,
) -> None:
    """Current Code Set B encoding should match the added golden fixtures."""
    symbol = Code128Encoder().encode(_build_payload(vector.input_data))

    assert _render_modules(vector) == vector.expected_modules
    assert symbol.metadata.display_text == vector.input_data
    assert symbol.matrix.height == 1