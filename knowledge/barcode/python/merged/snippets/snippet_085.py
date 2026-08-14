def test_ean13_parser_rejects_wrong_check_digit_when_flag_is_set() -> None:
    """A 13-digit string with an incorrect check digit must fail even with the flag enabled."""
    with pytest.raises(InvalidInputError, match="mismatch"):
        Ean13InputParser().parse(
            "4006381333939",
            options=Ean13Options(allow_check_digit_input=True),
        )