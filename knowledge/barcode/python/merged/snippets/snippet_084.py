def test_ean13_parser_rejects_13_digit_input_without_flag() -> None:
    """13-digit input is rejected by default; the message must name the enabling flag."""
    with pytest.raises(InvalidInputError, match="allow_check_digit_input"):
        Ean13InputParser().parse("4006381333931")