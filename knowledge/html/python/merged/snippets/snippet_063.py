def test_visibility_inherits(self) -> None:
        """visibility is an inherited property."""
        doc, parent, child = _doc_with_parent_child()
        parent.style.set_property("visibility", "hidden")

        child_style = child.get_computed_style()
        assert child_style.get_property_value("visibility") == "hidden"