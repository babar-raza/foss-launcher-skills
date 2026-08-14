def test_different_backgrounds_per_slide(tmp_pptx):
    """Each slide can have its own independent background."""
    pres = Presentation()
    # Add a second slide
    pres.slides.add_empty_slide(pres.slides[0].layout_slide)

    slide1 = pres.slides[0]
    slide1.background.type = BackgroundType.OWN_BACKGROUND
    slide1.background.fill_format.fill_type = FillType.SOLID
    slide1.background.fill_format.solid_fill_color.color = Color.red

    slide2 = pres.slides[1]
    slide2.background.type = BackgroundType.OWN_BACKGROUND
    slide2.background.fill_format.fill_type = FillType.SOLID
    slide2.background.fill_format.solid_fill_color.color = Color.blue

    pres2 = tmp_pptx(pres)
    c1 = pres2.slides[0].background.fill_format.solid_fill_color.color
    c2 = pres2.slides[1].background.fill_format.solid_fill_color.color
    assert c1.r == 255 and c1.b == 0  # red
    assert c2.r == 0 and c2.b == 255  # blue
    pres2.dispose()