def test_class_beats_type_selector(self) -> None:
        """Class selector .foo (0,1,0) beats type selector div (0,0,1)."""
        doc = Document()
        el = doc.create_element("div")
        el.set_attribute("class", "foo")
        doc.append_child(el)

        sheet = CSSStyleSheet()
        # Both rules in the same stylesheet; .foo has higher specificity.
        sheet.replace_sync("div { color: red } .foo { color: blue }")
        doc.attach_style_sheet(sheet)

        style = el.get_computed_style()
        assert style.get_property_value("color") == "blue", (
            "Class selector (0,1,0) must beat type selector (0,0,1)"
        )