def test_inline_only_resolves(self) -> None:
        """Inline-only declaration resolves without a stylesheet."""
        doc = Document()
        el = doc.create_element("div")
        doc.append_child(el)
        el.style.set_property("color", "green")
        style = el.get_computed_style()
        assert style.get_property_value("color") == "green"