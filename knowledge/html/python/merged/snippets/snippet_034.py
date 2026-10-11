def test_border_style_four_tokens() -> None:
    """border-style: solid dashed dotted double → all four individually."""
    el = _make_element("border-style: solid dashed dotted double")
    style = el.get_computed_style()
    assert style.get_property_value("border-top-style") == "solid"
    assert style.get_property_value("border-right-style") == "dashed"
    assert style.get_property_value("border-bottom-style") == "dotted"
    assert style.get_property_value("border-left-style") == "double"