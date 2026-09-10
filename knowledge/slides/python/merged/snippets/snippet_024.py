def test_clearing_a_shape_hyperlink_removes_its_relationship(produced, shape_on_blank_slide):
    """Setting the link back to None must take the .rels entry with it."""
    pres, shape = shape_on_blank_slide()
    shape.hyperlink_click = URL
    shape.hyperlink_click = None
    pkg = produced(pres)

    assert not pkg.findall(SLIDE, "//p:cNvPr/a:hlinkClick"), (
        "the hyperlink element survived being cleared"
    )
    external = [
        rel for rel in pkg.relationships(SLIDE).values()
        if rel["type"] == REL_TYPE["hyperlink"]
    ]
    assert not external, (
        "the element is gone but its external relationship is still declared: "
        "%r" % external
    )
    pkg.assert_package_is_consistent()