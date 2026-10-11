def test_revert_on_non_inherited_acts_as_initial(self) -> None:
        """background-color: revert returns '' (non-inherited → initial, no UA sheet)."""
        doc, _parent, child = _doc_with_parent_child()
        child.style.set_property("background-color", "revert")

        child_style = child.get_computed_style()
        assert child_style.get_property_value("background-color") == ""