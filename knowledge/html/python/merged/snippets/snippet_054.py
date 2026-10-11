def test_no_rule_no_property(self) -> None:
        """Element with no matching rules has no color in computed style."""
        doc = Document()
        el = doc.create_element("span")
        doc.append_child(el)
        style = el.get_computed_style()
        assert style.get_property_value("color") == ""