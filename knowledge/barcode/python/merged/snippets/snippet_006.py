def test_default_barcode_service_generates_and_renders_ean_upc_symbols(
    symbology: str,
    data: str,
    expected_width: int,
    expected_data: str,
) -> None:
    """The default service should run EAN/UPC through parse, encode, and SVG rendering."""
    service = build_default_service()

    barcode = service.generate(symbology, data)
    svg = barcode.to_svg()

    assert barcode.profile.status == "beta"
    assert barcode.symbol.metadata.normalized_data == expected_data
    assert barcode.symbol.matrix.width == expected_width
    assert barcode.symbol.matrix.height == 2
    assert svg.startswith("<svg")
    assert "<rect" in svg