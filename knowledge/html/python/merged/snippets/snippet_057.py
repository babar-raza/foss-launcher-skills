def test_important_without_inline(self) -> None:
        """Author !important rule wins over a later non-important author rule."""
        doc = Document()
        el = doc.create_element("div")
        doc.append_child(el)

        sheet = CSSStyleSheet()
        sheet.replace_sync("div { color: red !important } div { color: blue }")
        doc.attach_style_sheet(sheet)

        style = el.get_computed_style()
        assert style.get_property_value("color") == "red"