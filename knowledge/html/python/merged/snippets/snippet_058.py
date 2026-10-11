def test_author_stylesheet_property_resolves(self) -> None:
        """Renaming origin from 'stylesheet' to 'author' does not break normal stylesheet cascade."""
        doc = Document()
        el = doc.create_element("div")
        doc.append_child(el)

        sheet = CSSStyleSheet()
        sheet.replace_sync("div { color: teal }")
        doc.attach_style_sheet(sheet)

        style = el.get_computed_style()
        assert style.get_property_value("color") == "teal"