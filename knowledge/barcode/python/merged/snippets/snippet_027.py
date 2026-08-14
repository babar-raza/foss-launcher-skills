def test_code128_encoder_rejects_invalid_payload_contract(
    payload: NormalizedPayload,
) -> None:
    """Encoder contract violations should raise invalid-input errors."""
    with pytest.raises(InvalidInputError):
        Code128Encoder().encode(payload)