def test_code39_parser_rejects_base_out_of_set_characters(data: str, position: int) -> None:
    """Characters outside the 43-character base set should fail with a 1-based position."""
    with pytest.raises(InvalidInputError, match=f"position {position}"):
        _base_parser().parse(data)