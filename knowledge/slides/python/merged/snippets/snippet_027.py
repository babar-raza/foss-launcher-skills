def test_added_and_removed_slides_stay_registered(produced):
    """A slide is a slide in all four places, and removal cleans up all four."""
    pres = Presentation()
    pres.slides.add_empty_slide(pres.layout_slides[0])
    pres.slides.add_empty_slide(pres.layout_slides[0])
    pres.slides.remove_at(1)
    pkg = produced(pres)

    parts = pkg.parts_matching(r"^ppt/slides/slide\d+\.xml$")
    sld_ids = pkg.findall("ppt/presentation.xml", "//p:sldIdLst/p:sldId")
    slide_rels = [
        r for r in pkg.relationships("ppt/presentation.xml").values()
        if r["type"] == REL_TYPE["slide"]
    ]
    overrides = [
        n for n in pkg.content_types()[1]
        if n.startswith("/ppt/slides/slide")
    ]

    assert len(parts) == 2, parts
    assert len(sld_ids) == 2
    assert len(slide_rels) == 2
    assert len(overrides) == 2
    pkg.assert_package_is_consistent()