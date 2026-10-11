def test_group_properties_keep_their_schema_order_however_they_were_set(
    produced, blank_presentation, order
):
    """`<p:grpSpPr>` children follow `CT_GroupShapeProperties` for every permutation."""
    pres = blank_presentation
    group = pres.slides[0].shapes.add_group_shape()
    for operation in order:
        _apply(group, operation)
    pkg = produced(pres)

    grp_sp_pr = pkg.find_one(SLIDE, GRP_SP_PR)
    assert set(child_names(grp_sp_pr)) >= {"a:solidFill", "a:effectLst"}, (
        "the formatting children were not all written: %r" % child_names(grp_sp_pr)
    )
    pkg.assert_element(SLIDE, GRP_SP_PR, child_order=True)