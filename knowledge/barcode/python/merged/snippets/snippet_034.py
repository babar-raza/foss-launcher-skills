def test_code128_encoder_matches_auto_switching_golden_vectors(
    vector: Code128Vector,
) -> None:
    """AUTO mode with inter-set switching should match BWIPP golden fixtures."""
    actual = _render_modules(vector, encode_mode=Code128EncodeMode.AUTO)
    assert actual == vector.expected_modules