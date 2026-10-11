def test_an_embedded_image_resolves_from_the_slide(produced, test_data_dir):
    """`<a:blip r:embed>` must name a relationship that names a part that exists."""
    pres = Presentation()
    with open(os.path.join(test_data_dir, "lotus.png"), "rb") as fh:
        image = pres.images.add_image(fh.read())
    pres.slides[0].shapes.add_picture_frame(
        ShapeType.RECTANGLE, 50.0, 50.0, 200.0, 150.0, image
    )
    pkg = produced(pres)

    blip = pkg.find_one(SLIDE, "//a:blip")
    rel_id = blip.get(qname("r:embed"))
    assert rel_id, dict(blip.attrib)
    assert pkg.relationship(SLIDE, rel_id)["type"] == REL_TYPE["image"]
    pkg.assert_package_is_consistent()