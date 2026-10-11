def test_border_shorthand_regression() -> None:
    """border: 2px solid red still expands to all twelve longhands."""
    el = _make_element("border: 2px solid red")
    style = el.get_computed_style()
    for side in ("top", "right", "bottom", "left"):
        assert style.get_property_value(f"border-{side}-width") == "2px", (
            f"border-{side}-width should be '2px'"
        )
        assert style.get_property_value(f"border-{side}-style") == "solid", (
            f"border-{side}-style should be 'solid'"
        )
        assert style.get_property_value(f"border-{side}-color") == "red", (
            f"border-{side}-color should be 'red'"
        )