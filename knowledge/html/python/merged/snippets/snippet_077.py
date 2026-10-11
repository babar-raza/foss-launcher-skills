def test_revert_on_inherited_property_acts_as_inherit(self) -> None:
        """color: revert acts as inherit when parent has a color rule (no UA sheet)."""
        doc, parent, child = _doc_with_parent_child()
        parent.style.set_property("color", "navy")
        child.style.set_property("color", "revert")

        child_style = child.get_computed_style()
        assert child_style.get_property_value("color") == "navy", (
            "revert with no UA stylesheet falls back to unset semantics → inherit"
        )