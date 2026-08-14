def test_revert_on_text_align_on_root_returns_initial(self) -> None:
        """revert on root element (no parent) returns '' regardless of inherited status."""
        doc = Document()
        el = doc.create_element("div")
        doc.append_child(el)
        el.style.set_property("text-align", "revert")

        style = el.get_computed_style()
        assert style.get_property_value("text-align") == ""