def test_quotes_inherits(self) -> None:
        doc, parent, child = _doc_with_parent_child()
        parent.style.set_property("quotes", "none")
        assert child.get_computed_style().get_property_value("quotes") == "none"