def test_ean8_row1_guard_extension_mask(vector: Ean8Vector) -> None:
    symbol = Ean8Encoder().encode(_build_payload(vector.input_data))
    row1 = symbol.matrix.modules[1]
    actual_dark = {pos for pos, bit in enumerate(row1) if bit == 1}
    assert actual_dark == _GUARD_DARK_POSITIONS