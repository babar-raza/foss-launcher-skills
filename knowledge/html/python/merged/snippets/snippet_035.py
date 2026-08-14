def test_border_style_three_tokens() -> None:
    """border-style: solid dashed dotted → top 'solid', right/left 'dashed', bottom 'dotted'."""
    el = _make_element("border-style: solid dashed dotted")
    style = el.get_computed_style()
    assert style.get_property_value("border-top-style") == "solid"
    assert style.get_property_value("border-right-style") == "dashed"
    assert style.get_property_value("border-bottom-style") == "dotted"
    assert style.get_property_value("border-left-style") == "dashed"