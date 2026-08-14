def test_author_important_beats_inline_normal(self) -> None:
        """Author !important color:red wins over inline color:blue.

        !important flag (importance=1) beats non-important (importance=0)
        regardless of origin or specificity.
        """
        doc = Document()
        el = doc.create_element("div")
        doc.append_child(el)

        sheet = CSSStyleSheet()
        sheet.replace_sync("div { color: red !important }")
        doc.attach_style_sheet(sheet)

        el.style.set_property("color", "blue")

        style = el.get_computed_style()
        assert style.get_property_value("color") == "red", (
            "Author !important (importance=1) must outrank inline non-!important "
            "(importance=0) regardless of specificity"
        )