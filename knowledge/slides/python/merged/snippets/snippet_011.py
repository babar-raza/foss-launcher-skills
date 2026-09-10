def test_enabling_an_effect_writes_an_element_powerpoint_can_open(
    produced, shape_on_blank_slide, effect
):
    """The enabled effect must carry the attributes and children its type requires."""
    tag, required_attrs, one_of_children = REQUIRED[effect]

    pres, shape = shape_on_blank_slide()
    getattr(shape.effect_format, "enable_%s_effect" % effect)()
    pkg = produced(pres)

    element = pkg.find_one(SLIDE, "//a:effectLst/%s" % tag)

    for attribute in required_attrs:
        assert element.get(attribute) is not None, (
            "<%s> was written without its required @%s; ECMA-376 makes it "
            "mandatory and PowerPoint refuses the file. attributes: %r"
            % (tag, attribute, dict(element.attrib))
        )

    if one_of_children:
        present = child_names(element)
        assert any(name in present for name in one_of_children), (
            "<%s> was written with no %s child; ECMA-376 requires one and "
            "PowerPoint refuses the file. children: %r"
            % (tag, " / ".join(one_of_children), present)
        )