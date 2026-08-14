def test_border_color_single_token() -> None:
    """border-color: red broadcasts to all four border-*-color longhands (AC-6)."""
    el = _make_element("border-color: red")
    style = el.get_computed_style()
    assert style.get_property_value("border-top-color") == "red"
    assert style.get_property_value("border-right-color") == "red"
    assert style.get_property_value("border-bottom-color") == "red"
    assert style.get_property_value("border-left-color") == "red"