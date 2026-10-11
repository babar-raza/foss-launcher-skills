def test_code128_encoder_rejects_code_c_non_digit_input() -> None:
    """CODE_C mode with non-digit input should raise InvalidInputError from the parser."""
    payload = _build_payload("A", encode_mode=Code128EncodeMode.CODE_C)
    with pytest.raises(InvalidInputError):
        Code128Encoder().encode(payload)