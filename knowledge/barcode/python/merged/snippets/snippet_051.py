def test_code39_parser_accepts_every_base_sub_group() -> None:
    """A digit, an uppercase letter and the base symbols should all be accepted in base mode."""
    data = "Z-. $/+%"

    payload = _base_parser().parse(data)

    assert payload.code39_encode_mode is Code39EncodeMode.BASE
    assert payload.data == data