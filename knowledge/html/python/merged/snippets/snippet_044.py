def test_border_top_shorthand_regression() -> None:
    """border-top: 1px dashed blue still expands to its three longhands."""
    el = _make_element("border-top: 1px dashed blue")
    style = el.get_computed_style()
    assert style.get_property_value("border-top-width") == "1px"
    assert style.get_property_value("border-top-style") == "dashed"
    assert style.get_property_value("border-top-color") == "blue"