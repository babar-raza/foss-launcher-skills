def test_unset_on_color_acts_as_inherit(self) -> None:
        """color: unset on a child acts as inherit when parent has a color rule."""
        doc, parent, child = _doc_with_parent_child()
        parent.style.set_property("color", "green")
        child.style.set_property("color", "unset")

        child_style = child.get_computed_style()
        assert child_style.get_property_value("color") == "green", (
            "unset on inherited property must act as inherit"
        )