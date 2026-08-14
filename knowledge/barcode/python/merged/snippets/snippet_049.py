def test_code39_encoder_renders_display_text() -> None:
    """Display text should exclude sentinels/check char and escape control characters."""
    code_39_vector = next(
        vector for vector in CODE39_BASE_GOLDEN_VECTORS if vector.input_data == "CODE 39" and vector.add_check_digit
    )
    ht_vector = next(vector for vector in CODE39EXT_GOLDEN_VECTORS if vector.input_data == chr(9))
    del_vector = next(vector for vector in CODE39EXT_GOLDEN_VECTORS if vector.input_data == chr(127))

    code_39_symbol = Code39Encoder().encode(_build_payload(code_39_vector))
    ht_symbol = Code39Encoder().encode(_build_payload(ht_vector))
    del_symbol = Code39Encoder().encode(_build_payload(del_vector))

    assert code_39_symbol.metadata.display_text == "CODE 39"
    assert ht_symbol.metadata.display_text == "<HT>"
    assert del_symbol.metadata.display_text == "<DEL>"