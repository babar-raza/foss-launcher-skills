def test_border_color_three_tokens() -> None:
    """border-color: red green blue → top 'red', right/left 'green', bottom 'blue'."""
    el = _make_element("border-color: red green blue")
    style = el.get_computed_style()
    assert style.get_property_value("border-top-color") == "red"
    assert style.get_property_value("border-right-color") == "green"
    assert style.get_property_value("border-bottom-color") == "blue"
    assert style.get_property_value("border-left-color") == "green"