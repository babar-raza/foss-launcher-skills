def test_a_group_shape_has_no_extrusion_to_set(produced, blank_presentation):
    """`CT_GroupShapeProperties` has no `a:sp3d`, so none may be written."""
    pres = blank_presentation
    group = pres.slides[0].shapes.add_group_shape()

    assert group.three_d_format is None, (
        "three_d_format on a group shape returned %r; a:sp3d is not a child "
        "the type has" % (group.three_d_format,)
    )

    pkg = produced(pres)
    assert not pkg.findall(SLIDE, GRP_SP_PR + "/a:sp3d"), (
        "<a:sp3d> was written inside <p:grpSpPr>, which the schema does not "
        "allow: %r" % child_names(pkg.find_one(SLIDE, GRP_SP_PR))
    )