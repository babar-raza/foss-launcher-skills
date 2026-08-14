def test_ean8_row_heights_match_iso_constants(vector: Ean8Vector) -> None:
    symbol = Ean8Encoder().encode(_build_payload(vector.input_data))
    assert symbol.matrix.row_heights_x == pytest.approx((EAN8_BAR_HEIGHT_X, EAN_GUARD_EXTENSION_X))