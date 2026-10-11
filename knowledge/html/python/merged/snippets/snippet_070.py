def test_inherit_keyword_on_root_returns_initial(self) -> None:
        """inherit on a root element (no parent) returns initial value ('')."""
        doc = Document()
        el = doc.create_element("div")
        doc.append_child(el)
        el.style.set_property("color", "inherit")

        style = el.get_computed_style()
        assert style.get_property_value("color") == ""