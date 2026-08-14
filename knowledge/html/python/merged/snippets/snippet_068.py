def test_inherit_keyword_on_non_inherited_property(self) -> None:
        """background-color: inherit forces propagation even for non-inherited props."""
        doc, parent, child = _doc_with_parent_child()
        parent.style.set_property("background-color", "blue")
        child.style.set_property("background-color", "inherit")

        child_style = child.get_computed_style()
        assert child_style.get_property_value("background-color") == "blue", (
            "inherit keyword must force inheritance regardless of property class"
        )