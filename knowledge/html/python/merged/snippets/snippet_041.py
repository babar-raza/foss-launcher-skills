def test_css_supports_border_style() -> None:
    """CSS.supports('border-style', 'solid') returns True (AC-9)."""
    assert CSS.supports("border-style", "solid") is True