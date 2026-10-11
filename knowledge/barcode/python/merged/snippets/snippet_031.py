def test_code128_encoder_matches_code_set_c_golden_vectors(
    vector: Code128Vector,
) -> None:
    """Code Set C encoding should match BWIPP golden fixtures."""
    actual = _render_modules(vector, encode_mode=Code128EncodeMode.CODE_C)
    assert actual == vector.expected_modules