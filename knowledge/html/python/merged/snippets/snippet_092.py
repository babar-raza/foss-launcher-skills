def test_font_variant_inherits(self) -> None:
        doc, parent, child = _doc_with_parent_child()
        parent.style.set_property("font-variant", "small-caps")
        assert child.get_computed_style().get_property_value("font-variant") == "small-caps"