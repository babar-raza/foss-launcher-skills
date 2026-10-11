def test_initial_on_inherited_resets_to_empty(self) -> None:
        """color: initial ignores parent color and returns initial value ('')."""
        doc, parent, child = _doc_with_parent_child()
        parent.style.set_property("color", "red")
        child.style.set_property("color", "initial")

        child_style = child.get_computed_style()
        assert child_style.get_property_value("color") == "", (
            "initial must return the CSS initial value ('' in this implementation)"
        )