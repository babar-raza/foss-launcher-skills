def test_background_color_does_not_inherit(self) -> None:
        """background-color is non-inherited; child gets '' when parent has it."""
        doc, parent, child = _doc_with_parent_child()
        parent.style.set_property("background-color", "red")

        child_style = child.get_computed_style()
        assert child_style.get_property_value("background-color") == "", (
            "background-color is non-inherited; must not appear on child"
        )