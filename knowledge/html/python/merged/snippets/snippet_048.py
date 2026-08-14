def test_inline_important_beats_author_important_by_specificity(self) -> None:
        """Inline !important beats author-stylesheet !important via specificity.

        Per CSS Cascade Level 4 §6.4.2, inline is author origin with
        specificity (1,0,0).  Author stylesheet type-selector specificity
        is (0,0,1).  When both are !important and share origin='author',
        the higher specificity wins: inline (1,0,0) > stylesheet (0,0,1).
        """
        doc = Document()
        el = doc.create_element("div")
        doc.append_child(el)

        sheet = CSSStyleSheet()
        sheet.replace_sync("div { color: red !important }")
        doc.attach_style_sheet(sheet)

        # Inline style value includes !important — _normalize_declaration strips it.
        el.style.set_property("color", "blue !important")

        style = el.get_computed_style()
        # Inline !important (1,0,0) beats stylesheet !important (0,0,1)
        assert style.get_property_value("color") == "blue", (
            "Inline !important with specificity (1,0,0) must beat author "
            "stylesheet !important with type-selector specificity (0,0,1)"
        )