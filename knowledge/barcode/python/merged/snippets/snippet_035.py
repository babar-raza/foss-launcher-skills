def test_code128_encoder_rejects_code_c_odd_length_input() -> None:
    """CODE_C mode with odd-length digit input should raise InvalidInputError."""
    with pytest.raises(InvalidInputError):
        Code128Encoder().encode(_build_payload("123", encode_mode=Code128EncodeMode.CODE_C))