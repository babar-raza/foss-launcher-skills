def test_inherit_keyword_on_inherited_property(self) -> None:
        """inherit on an already-inherited property also uses parent value."""
        doc, parent, child = _doc_with_parent_child()
        parent.style.set_property("color", "green")
        child.style.set_property("color", "inherit")

        child_style = child.get_computed_style()
        assert child_style.get_property_value("color") == "green"