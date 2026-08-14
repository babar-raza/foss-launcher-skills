def test_code128_encoder_rejects_code_a_lowercase() -> None:
    """CODE_A mode with a lowercase character (Code Set B-only) should raise InvalidInputError."""
    with pytest.raises(InvalidInputError):
        Code128Encoder().encode(_build_payload("a", encode_mode=Code128EncodeMode.CODE_A))