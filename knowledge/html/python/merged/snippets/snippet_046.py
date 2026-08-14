def test_inline_beats_class_selector_author_rule(self) -> None:
        """Inline color:blue wins over author stylesheet .foo { color:red }.

        A class selector has specificity (0,1,0) which is less than the
        inline specificity (1,0,0), so inline wins.
        """
        doc = Document()
        el = doc.create_element("div")
        el.set_attribute("class", "foo")
        doc.append_child(el)

        sheet = CSSStyleSheet()
        sheet.replace_sync(".foo { color: red }")
        doc.attach_style_sheet(sheet)

        el.style.set_property("color", "blue")

        style = el.get_computed_style()
        assert style.get_property_value("color") == "blue", (
            "Inline (1,0,0) must beat class selector (0,1,0)"
        )