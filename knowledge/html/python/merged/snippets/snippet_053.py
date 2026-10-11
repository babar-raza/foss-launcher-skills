def test_later_stylesheet_wins_same_specificity(self) -> None:
        """When specificity is equal, a rule from a later stylesheet wins."""
        doc = Document()
        el = doc.create_element("div")
        doc.append_child(el)

        sheet1 = CSSStyleSheet()
        sheet1.replace_sync("div { color: red }")
        sheet2 = CSSStyleSheet()
        sheet2.replace_sync("div { color: blue }")
        doc.attach_style_sheet(sheet1)
        doc.attach_style_sheet(sheet2)

        style = el.get_computed_style()
        assert style.get_property_value("color") == "blue", (
            "Rule from later-attached stylesheet must win when specificity is equal"
        )