def test_code128_public_result_renders_to_svg() -> None:
    """The public Code 128 result should render directly to SVG."""
    svg = barcode.code128("A").to_svg()

    root = ET.fromstring(svg)
    text = root.find(f".//{{{SVG_NAMESPACE}}}text")

    assert root.tag == f"{{{SVG_NAMESPACE}}}svg"
    assert text is not None
    assert text.text == "A"