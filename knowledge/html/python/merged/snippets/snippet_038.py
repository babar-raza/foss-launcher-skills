def test_border_color_two_tokens() -> None:
    """border-color: red green → top/bottom 'red', right/left 'green'."""
    el = _make_element("border-color: red green")
    style = el.get_computed_style()
    assert style.get_property_value("border-top-color") == "red"
    assert style.get_property_value("border-right-color") == "green"
    assert style.get_property_value("border-bottom-color") == "red"
    assert style.get_property_value("border-left-color") == "green"