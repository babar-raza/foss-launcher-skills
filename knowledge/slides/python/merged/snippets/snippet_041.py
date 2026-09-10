def test_a_shape_with_depth_gets_the_scene_that_makes_it_render(
    produced, shape_on_blank_slide
):
    """Extrusion without a scene is invisible; `<a:scene3d>` must be written too."""
    pres, shape = shape_on_blank_slide()
    shape.three_d_format.depth = 6.0
    shape.three_d_format.extrusion_height = 8.0
    shape.three_d_format.contour_width = 2.0
    pkg = produced(pres)

    sp_pr = pkg.find_one(SLIDE, "//p:sp/p:spPr")
    present = child_names(sp_pr)
    assert "a:sp3d" in present, "no <a:sp3d> was written at all: %r" % present
    assert "a:scene3d" in present, (
        "<a:sp3d> was written with no <a:scene3d> sibling, so the shape has no "
        "camera and no lighting and PowerPoint renders it flat. "
        "children of <p:spPr>: %r" % present
    )

    pkg.assert_element(
        SLIDE,
        "//a:scene3d",
        children=("a:camera", "a:lightRig"),
        child_order=True,
    )
    pkg.assert_element(SLIDE, "//a:scene3d/a:camera", attrs={"prst": ...})
    pkg.assert_element(SLIDE, "//a:scene3d/a:lightRig", attrs={"rig": ..., "dir": ...})
    pkg.assert_element(SLIDE, "//p:sp/p:spPr", child_order=True)