def test_ean8_matrix_dimensions(vector: Ean8Vector) -> None:
    symbol = Ean8Encoder().encode(_build_payload(vector.input_data))
    assert symbol.matrix.width == 67
    assert symbol.matrix.height == 2