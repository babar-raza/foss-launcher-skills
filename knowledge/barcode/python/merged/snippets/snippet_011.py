def test_generate_returns_a_public_code128_barcode() -> None:
    """The generic public entrypoint should return a real Code 128 barcode."""
    barcode_obj = barcode.generate("code128", "A")

    assert isinstance(barcode_obj, barcode.Barcode)
    assert barcode_obj.profile.name == "code128"
    assert barcode_obj.symbol.metadata.display_text == "A"