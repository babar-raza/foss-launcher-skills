def test_unset_on_text_align_acts_as_inherit(self) -> None:
        """text-align: unset acts as inherit (newly inherited property in )."""
        doc, parent, child = _doc_with_parent_child()
        parent.style.set_property("text-align", "right")
        child.style.set_property("text-align", "unset")

        child_style = child.get_computed_style()
        assert child_style.get_property_value("text-align") == "right"