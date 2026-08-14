def test_compound_selector_beats_type_selector(self) -> None:
        """div.foo (0,1,1) beats div (0,0,1)."""
        doc = Document()
        el = doc.create_element("div")
        el.set_attribute("class", "foo")
        doc.append_child(el)

        sheet = CSSStyleSheet()
        sheet.replace_sync("div { color: red } div.foo { color: blue }")
        doc.attach_style_sheet(sheet)

        style = el.get_computed_style()
        assert style.get_property_value("color") == "blue", (
            "Compound selector div.foo (0,1,1) must beat type selector div (0,0,1)"
        )