def test_border_width_four_tokens() -> None:
    """border-width: 1px 2px 3px 4px assigns top/right/bottom/left individually (AC-2)."""
    el = _make_element("border-width: 1px 2px 3px 4px")
    style = el.get_computed_style()
    assert style.get_property_value("border-top-width") == "1px"
    assert style.get_property_value("border-right-width") == "2px"
    assert style.get_property_value("border-bottom-width") == "3px"
    assert style.get_property_value("border-left-width") == "4px"