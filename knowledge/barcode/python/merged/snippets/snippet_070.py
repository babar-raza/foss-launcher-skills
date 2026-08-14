def test_ean13_metadata_fields(vector: Ean13Vector) -> None:
    """Symbol metadata must reflect the normalized 13-digit input and display text."""
    symbol = Ean13Encoder().encode(_build_payload(vector.input_data))

    assert symbol.metadata.symbology == "ean13"
    assert symbol.metadata.input_kind == "text"
    assert symbol.metadata.normalized_data == vector.input_data
    assert symbol.metadata.display_text == vector.input_data