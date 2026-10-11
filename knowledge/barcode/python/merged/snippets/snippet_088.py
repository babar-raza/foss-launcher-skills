def test_ean8_row0_matches_golden_module_string(vector: Ean8Vector) -> None:
    symbol = Ean8Encoder().encode(_build_payload(vector.input_data))
    actual_row0 = "".join(str(bit) for bit in symbol.matrix.modules[0])
    assert actual_row0 == vector.expected_row0