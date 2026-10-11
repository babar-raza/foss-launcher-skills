def test_css_supports_border_color() -> None:
    """CSS.supports('border-color', 'red') returns True (AC-10)."""
    assert CSS.supports("border-color", "red") is True