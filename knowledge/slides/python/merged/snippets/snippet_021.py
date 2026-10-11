def test_a_child_of_a_group_still_has_both(produced, blank_presentation):
    """The restriction is the group's own properties, not the shapes inside it."""
    from aspose.slides_foss import ShapeType

    pres = blank_presentation
    group = pres.slides[0].shapes.add_group_shape()
    child = group.shapes.add_auto_shape(ShapeType.RECTANGLE, 10.0, 10.0, 100.0, 50.0)
    child.line_format.width = 3.0
    child.three_d_format.depth = 6.0
    pkg = produced(pres)

    sp_pr = pkg.find_one(SLIDE, "//p:grpSp/p:sp/p:spPr")
    present = child_names(sp_pr)
    assert "a:ln" in present and "a:sp3d" in present, (
        "a shape inside a group lost its outline or its extrusion: %r" % present
    )
    pkg.assert_element(SLIDE, "//p:grpSp/p:sp/p:spPr", child_order=True)