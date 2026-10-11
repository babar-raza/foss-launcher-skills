def test_a_fill_set_after_a_scene_still_precedes_it(produced, blank_presentation):
    """A fill added to a group that already has a scene must go in before it.

    A loaded deck can arrive with `<a:scene3d>` already in place; appending the
    fill after it is the inversion the sequence forbids.
    """
    import lxml.etree as ET

    pres = blank_presentation
    group = pres.slides[0].shapes.add_group_shape()
    grp_sp_pr = group._get_sp_pr()
    ET.SubElement(grp_sp_pr, "{http://schemas.openxmlformats.org/drawingml/2006/main}scene3d")
    group.fill_format.fill_type = FillType.SOLID
    pkg = produced(pres)

    pkg.assert_element(SLIDE, GRP_SP_PR, child_order=True)