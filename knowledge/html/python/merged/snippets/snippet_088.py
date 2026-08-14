def test_pointer_events_inherits(self) -> None:
        doc, parent, child = _doc_with_parent_child()
        parent.style.set_property("pointer-events", "none")
        assert child.get_computed_style().get_property_value("pointer-events") == "none"