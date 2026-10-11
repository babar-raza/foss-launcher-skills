def test_code128_encoder_matches_fnc_golden_vectors(
    vector: Code128Vector,
    encode_mode: Code128EncodeMode,
) -> None:
    """FNC sentinel encoding should match BWIPP golden fixtures."""
    encoder = Code128Encoder()
    symbol = encoder.encode(_build_payload(vector.input_data, encode_mode=encode_mode))
    actual_rows = tuple("".join(str(m) for m in row) for row in symbol.matrix.modules)

    assert actual_rows == vector.expected_modules
    assert "<FNC1>" in symbol.metadata.display_text