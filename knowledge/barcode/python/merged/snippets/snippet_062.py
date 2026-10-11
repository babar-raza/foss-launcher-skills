def test_code39_parser_rejects_non_ascii_in_full_ascii_mode() -> None:
    """Full-ASCII mode should reject code points above 127."""
    with pytest.raises(InvalidInputError, match="position 1"):
        _ext_parser().parse("é")