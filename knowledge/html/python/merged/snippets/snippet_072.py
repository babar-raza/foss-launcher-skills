def test_initial_on_non_inherited_returns_empty(self) -> None:
        """background-color: initial returns '' (the CSS initial value here)."""
        doc, _parent, child = _doc_with_parent_child()
        child.style.set_property("background-color", "initial")

        child_style = child.get_computed_style()
        assert child_style.get_property_value("background-color") == ""