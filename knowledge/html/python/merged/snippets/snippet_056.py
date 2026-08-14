def test_shorthand_expansion_still_works(self) -> None:
        """Shorthand margin expansion is unaffected by the origin change."""
        doc = Document()
        el = doc.create_element("div")
        doc.append_child(el)

        sheet = CSSStyleSheet()
        sheet.replace_sync("div { margin: 4px 8px }")
        doc.attach_style_sheet(sheet)

        style = el.get_computed_style()
        assert style.get_property_value("margin-top") == "4px"
        assert style.get_property_value("margin-right") == "8px"
        assert style.get_property_value("margin-bottom") == "4px"
        assert style.get_property_value("margin-left") == "8px"