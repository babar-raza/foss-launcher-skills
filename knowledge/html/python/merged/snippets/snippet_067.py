def test_margin_top_does_not_inherit(self) -> None:
        """margin-top is non-inherited; child should not receive parent margin."""
        doc, parent, child = _doc_with_parent_child()
        parent.style.set_property("margin-top", "20px")

        child_style = child.get_computed_style()
        assert child_style.get_property_value("margin-top") == ""