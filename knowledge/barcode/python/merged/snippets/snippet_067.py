def test_ean13_matrix_dimensions(vector: Ean13Vector) -> None:
    """EAN-13 matrix must be exactly 95 modules wide and 2 rows tall."""
    symbol = Ean13Encoder().encode(_build_payload(vector.input_data))

    assert symbol.matrix.width == 95
    assert symbol.matrix.height == 2