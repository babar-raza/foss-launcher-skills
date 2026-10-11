def test_code128_encoder_rejects_unsupported_text_characters(input_data: str) -> None:
    """Unsupported characters should fail with the typed input error."""
    payload = _build_payload(input_data)

    with pytest.raises(InvalidInputError, match="character"):
        Code128Encoder().encode(payload)