def test_color_propagates_through_two_ancestor_levels(self) -> None:
        """grandparent color propagates via parent to child (two hops)."""
        doc, grandparent, parent, child = _doc_with_grandparent_parent_child()
        sheet = CSSStyleSheet()
        sheet.replace_sync("div { color: teal }")
        doc.attach_style_sheet(sheet)

        # The grandparent rule sets color: teal; parent inherits it; child inherits
        # from parent (which already resolved teal from grandparent).
        child_style = child.get_computed_style()
        assert child_style.get_property_value("color") == "teal"