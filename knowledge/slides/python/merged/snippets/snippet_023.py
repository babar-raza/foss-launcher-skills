def test_a_shape_level_hyperlink_reaches_the_package(produced, shape_on_blank_slide):
    """A link on the whole shape lives in `p:cNvPr`, not in the run properties.

    `CT_NonVisualDrawingProps` (ECMA-376 §20.1.2.2.8) is `hlinkClick?`,
    `hlinkHover?`, `extLst?` — and the mouse-over element is named
    `a:hlinkHover` there, not `a:hlinkMouseOver` as it is on a text run. The
    two names are easy to write interchangeably and only one of them is the
    element PowerPoint reads.
    """
    pres, shape = shape_on_blank_slide()
    shape.hyperlink_click = URL
    shape.hyperlink_mouse_over = URL + "/over"
    pkg = produced(pres)

    for tag, expected in (("a:hlinkClick", URL), ("a:hlinkHover", URL + "/over")):
        element = pkg.find_one(SLIDE, "//p:sp/p:nvSpPr/p:cNvPr/" + tag)
        rel_id = element.get(qname("r:id"))
        assert rel_id, "<%s> carries no r:id: %r" % (tag, dict(element.attrib))
        relationship = pkg.relationship(SLIDE, rel_id)
        assert relationship["type"] == REL_TYPE["hyperlink"]
        assert relationship["mode"] == "External"
        assert relationship["target"] == expected

    assert not pkg.findall(SLIDE, "//p:cNvPr/a:hlinkMouseOver"), (
        "a:hlinkMouseOver is the run-properties name; CT_NonVisualDrawingProps "
        "has no such child and PowerPoint ignores it"
    )
    pkg.assert_element(
        SLIDE,
        "//p:sp/p:nvSpPr/p:cNvPr",
        child_order=[["a:hlinkClick"], ["a:hlinkHover"], ["a:extLst"]],
    )
    pkg.assert_package_is_consistent()