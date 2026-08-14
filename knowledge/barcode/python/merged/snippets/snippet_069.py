def test_ean13_row1_guard_extension_mask(vector: Ean13Vector) -> None:
    """Row 1 must have dark modules only at guard-bar extension positions {0,2,46,48,92,94}."""
    symbol = Ean13Encoder().encode(_build_payload(vector.input_data))
    row1 = symbol.matrix.modules[1]

    actual_dark = {pos for pos, bit in enumerate(row1) if bit == 1}
    assert actual_dark == _GUARD_DARK_POSITIONS