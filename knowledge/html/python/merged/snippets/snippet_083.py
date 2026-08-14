def test_child_local_rule_overrides_deep_inherited_value(self) -> None:
        """child local rule overrides value inherited from grandparent."""
        doc, grandparent, parent, child = _doc_with_grandparent_parent_child()
        grandparent.style.set_property("color", "blue")
        child.style.set_property("color", "orange")

        child_style = child.get_computed_style()
        assert child_style.get_property_value("color") == "orange"