def test_list_style_type_inherits_to_child(self) -> None:
        """list-style-type is an inherited property; li inherits from ul."""
        doc = Document()
        ul = doc.create_element("ul")
        li = doc.create_element("li")
        doc.append_child(ul)
        ul.append_child(li)

        sheet = CSSStyleSheet()
        sheet.replace_sync("ul { list-style-type: square }")
        doc.attach_style_sheet(sheet)

        li_style = li.get_computed_style()
        assert li_style.get_property_value("list-style-type") == "square"