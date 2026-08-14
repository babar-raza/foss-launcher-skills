def test_code128_encoder_rejects_reference_invalid_text_cases(
    input_data: str,
) -> None:
    """Non-Code-128 Unicode inputs from the fixture pack should fail predictably."""
    with pytest.raises(InvalidInputError, match="unsupported Code 128 character"):
        Code128Encoder().encode(_build_payload(input_data))