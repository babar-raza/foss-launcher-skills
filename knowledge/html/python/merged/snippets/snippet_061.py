def test_text_align_inherits_to_child(self) -> None:
        """text-align is in _INHERITED_PROPERTIES; child must receive parent value."""
        doc, parent, child = _doc_with_parent_child()
        sheet = CSSStyleSheet()
        sheet.replace_sync("div { text-align: center }")
        doc.attach_style_sheet(sheet)

        child_style = child.get_computed_style()
        assert child_style.get_property_value("text-align") == "center"