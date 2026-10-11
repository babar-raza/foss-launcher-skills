def test_an_enabled_effect_does_not_disturb_the_effect_sequence(
    produced, shape_on_blank_slide, effect
):
    """`<a:effectLst>` children stay in their ECMA-376 sequence."""
    pres, shape = shape_on_blank_slide()
    shape.effect_format.set_blur_effect(4.0, False)
    getattr(shape.effect_format, "enable_%s_effect" % effect)()
    getattr(shape.effect_format, "enable_soft_edge_effect")()
    pkg = produced(pres)

    pkg.assert_element(SLIDE, "//a:effectLst", child_order=True)