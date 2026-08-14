def test_clear_background(tmp_pptx):
    """Setting NOT_DEFINED removes the background element."""
    pres = Presentation()
    slide = pres.slides[0]
    slide.background.type = BackgroundType.OWN_BACKGROUND
    slide.background.fill_format.fill_type = FillType.SOLID
    slide.background.fill_format.solid_fill_color.color = Color.red

    # Now clear it
    slide.background.type = BackgroundType.NOT_DEFINED

    pres2 = tmp_pptx(pres)
    assert pres2.slides[0].background.type == BackgroundType.NOT_DEFINED
    pres2.dispose()