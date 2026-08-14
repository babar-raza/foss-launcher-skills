def test_border_collapse_inherits(self) -> None:
        doc, parent, child = _doc_with_parent_child("table", "tr")
        parent.style.set_property("border-collapse", "collapse")
        assert child.get_computed_style().get_property_value("border-collapse") == "collapse"