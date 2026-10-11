def test_id_beats_class_selector(self) -> None:
        """ID selector #bar (1,0,0) beats class selector .foo (0,1,0)."""
        doc = Document()
        el = doc.create_element("div")
        el.set_attribute("class", "foo")
        el.set_attribute("id", "bar")
        doc.append_child(el)

        sheet = CSSStyleSheet()
        sheet.replace_sync(".foo { color: red } #bar { color: blue }")
        doc.attach_style_sheet(sheet)

        style = el.get_computed_style()
        assert style.get_property_value("color") == "blue", (
            "ID selector (1,0,0) must beat class selector (0,1,0)"
        )