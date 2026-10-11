def test_code128_encoder_reference_behavior_vectors(
    vector: Code128Vector,
) -> None:
    """AUTO-mode reference fixtures should match their known-good module sequence."""
    assert _render_modules(vector, encode_mode=Code128EncodeMode.AUTO) == vector.expected_modules