def test_css_supports_border_width() -> None:
    """CSS.supports('border-width', '1px') returns True (AC-8)."""
    assert CSS.supports("border-width", "1px") is True