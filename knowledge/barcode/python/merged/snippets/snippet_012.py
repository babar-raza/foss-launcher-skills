def test_code128_helper_returns_a_public_code128_barcode() -> None:
    """The dedicated helper should return the same public result shape."""
    barcode_obj = barcode.code128("A")

    assert isinstance(barcode_obj, barcode.Barcode)
    assert barcode_obj.profile.name == "code128"
    assert barcode_obj.symbol.metadata.display_text == "A"