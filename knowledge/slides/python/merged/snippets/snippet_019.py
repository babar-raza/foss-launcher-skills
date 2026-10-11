def test_a_group_shape_has_no_outline_to_set(produced, blank_presentation):
    """`CT_GroupShapeProperties` has no `a:ln`, so none may be written."""
    pres = blank_presentation
    group = pres.slides[0].shapes.add_group_shape()

    assert group.line_format is None, (
        "line_format on a group shape returned %r; there is nowhere valid to "
        "put the result, so the documented None is the only honest answer"
        % (group.line_format,)
    )

    pkg = produced(pres)
    assert not pkg.findall(SLIDE, GRP_SP_PR + "/a:ln"), (
        "<a:ln> was written inside <p:grpSpPr>, which the schema does not "
        "allow: %r" % child_names(pkg.find_one(SLIDE, GRP_SP_PR))
    )