def test_direction_inherits(self) -> None:
        doc, parent, child = _doc_with_parent_child()
        parent.style.set_property("direction", "rtl")
        assert child.get_computed_style().get_property_value("direction") == "rtl"