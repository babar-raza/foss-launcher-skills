def test_nearest_ancestor_wins_in_deep_chain(self) -> None:
        """Parent color beats grandparent color in a two-level inheritance chain."""
        doc, grandparent, parent, child = _doc_with_grandparent_parent_child()
        grandparent.style.set_property("color", "blue")
        parent.style.set_property("color", "red")

        child_style = child.get_computed_style()
        assert child_style.get_property_value("color") == "red", (
            "nearest ancestor value must win over more-distant ancestor"
        )