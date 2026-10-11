def test_white_space_inherits(self) -> None:
        doc, parent, child = _doc_with_parent_child()
        parent.style.set_property("white-space", "nowrap")
        assert child.get_computed_style().get_property_value("white-space") == "nowrap"