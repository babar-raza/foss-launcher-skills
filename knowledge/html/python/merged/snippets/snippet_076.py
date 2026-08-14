def test_unset_on_margin_top_acts_as_initial(self) -> None:
        """margin-top: unset returns '' (non-inherited → initial)."""
        doc, _parent, child = _doc_with_parent_child()
        child.style.set_property("margin-top", "unset")

        child_style = child.get_computed_style()
        assert child_style.get_property_value("margin-top") == ""