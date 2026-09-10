def test_a_light_rig_carries_its_required_direction(produced, shape_on_blank_slide):
    """`CT_LightRig` requires `@dir` as well as `@rig`."""
    pres, shape = shape_on_blank_slide()
    shape.three_d_format.light_rig.light_type = LightRigPresetType.THREE_PT
    pkg = produced(pres)

    pkg.assert_element(SLIDE, "//a:lightRig", attrs={"rig": ..., "dir": ...})