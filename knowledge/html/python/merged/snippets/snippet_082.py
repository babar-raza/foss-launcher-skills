def test_text_align_propagates_through_two_levels(self) -> None:
        """text-align set on grandparent propagates through parent to grandchild."""
        doc, grandparent, parent, child = _doc_with_grandparent_parent_child()
        grandparent.style.set_property("text-align", "justify")

        child_style = child.get_computed_style()
        assert child_style.get_property_value("text-align") == "justify"