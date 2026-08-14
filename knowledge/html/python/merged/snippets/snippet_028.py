def test_border_width_single_token() -> None:
    """border-width: 2px broadcasts to all four border-*-width longhands (AC-1)."""
    el = _make_element("border-width: 2px")
    style = el.get_computed_style()
    assert style.get_property_value("border-top-width") == "2px"
    assert style.get_property_value("border-right-width") == "2px"
    assert style.get_property_value("border-bottom-width") == "2px"
    assert style.get_property_value("border-left-width") == "2px"