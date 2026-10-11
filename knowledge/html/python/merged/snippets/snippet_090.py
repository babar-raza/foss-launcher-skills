def test_writing_mode_inherits(self) -> None:
        doc, parent, child = _doc_with_parent_child()
        parent.style.set_property("writing-mode", "vertical-rl")
        assert child.get_computed_style().get_property_value("writing-mode") == "vertical-rl"