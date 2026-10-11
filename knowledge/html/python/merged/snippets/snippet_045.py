def test_inline_beats_type_selector_author_rule(self) -> None:
        """Inline color:blue wins over author stylesheet div { color:red }.

        Inline declarations are origin='author' with specificity (1,0,0).
        The type selector 'div' has specificity (0,0,1) which is lower,
        so the inline declaration wins.
        """
        doc = Document()
        el = doc.create_element("div")
        doc.append_child(el)

        sheet = CSSStyleSheet()
        sheet.replace_sync("div { color: red }")
        doc.attach_style_sheet(sheet)

        el.style.set_property("color", "blue")

        style = el.get_computed_style()
        assert style.get_property_value("color") == "blue", (
            "Inline declaration (author origin, specificity (1,0,0)) must beat "
            "author stylesheet type selector rule (specificity (0,0,1))"
        )