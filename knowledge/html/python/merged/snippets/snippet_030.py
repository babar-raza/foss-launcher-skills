def test_border_width_two_tokens() -> None:
    """border-width: 1px 2px → top/bottom '1px', right/left '2px' (AC-3)."""
    el = _make_element("border-width: 1px 2px")
    style = el.get_computed_style()
    assert style.get_property_value("border-top-width") == "1px"
    assert style.get_property_value("border-right-width") == "2px"
    assert style.get_property_value("border-bottom-width") == "1px"
    assert style.get_property_value("border-left-width") == "2px"