def test_ean8_metadata_fields(vector: Ean8Vector) -> None:
    symbol = Ean8Encoder().encode(_build_payload(vector.input_data))
    assert symbol.metadata.symbology == "ean8"
    assert symbol.metadata.input_kind == "text"
    assert symbol.metadata.normalized_data == vector.input_data
    assert symbol.metadata.display_text == vector.input_data