def test_word_break_inherits(self) -> None:
        doc, parent, child = _doc_with_parent_child()
        parent.style.set_property("word-break", "break-all")
        assert child.get_computed_style().get_property_value("word-break") == "break-all"