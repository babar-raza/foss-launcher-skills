def test_an_enabled_effect_leaves_the_package_consistent(produced, shape_on_blank_slide):
    """Enabling every effect must not break relationships or content types."""
    pres, shape = shape_on_blank_slide()
    for effect in sorted(REQUIRED):
        getattr(shape.effect_format, "enable_%s_effect" % effect)()
    pkg = produced(pres)

    pkg.assert_package_is_consistent()