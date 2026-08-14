def test_letter_spacing_inherits(self) -> None:
        doc, parent, child = _doc_with_parent_child()
        parent.style.set_property("letter-spacing", "2px")
        assert child.get_computed_style().get_property_value("letter-spacing") == "2px"