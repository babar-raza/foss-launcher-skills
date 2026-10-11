def test_cursor_inherits(self) -> None:
        doc, parent, child = _doc_with_parent_child()
        parent.style.set_property("cursor", "pointer")
        assert child.get_computed_style().get_property_value("cursor") == "pointer"