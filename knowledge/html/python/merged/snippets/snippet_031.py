def test_border_width_three_tokens() -> None:
    """border-width: 1px 2px 3px → top '1px', right/left '2px', bottom '3px'."""
    el = _make_element("border-width: 1px 2px 3px")
    style = el.get_computed_style()
    assert style.get_property_value("border-top-width") == "1px"
    assert style.get_property_value("border-right-width") == "2px"
    assert style.get_property_value("border-bottom-width") == "3px"
    assert style.get_property_value("border-left-width") == "2px"