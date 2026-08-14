def test_code128_encoder_rejects_auto_del_character() -> None:
    """AUTO mode with DEL (0x7F) should raise InvalidInputError — DEL is not in any Code 128 code set."""
    with pytest.raises(InvalidInputError):
        Code128Encoder().encode(_build_payload("\x7f", encode_mode=Code128EncodeMode.AUTO))