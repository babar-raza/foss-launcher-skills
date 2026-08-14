def test_change_background_type(tmp_pptx):
    """Changing background type clears previous data."""
    pres = Presentation()
    slide = pres.slides[0]

    # Start with solid
    slide.background.type = BackgroundType.OWN_BACKGROUND
    slide.background.fill_format.fill_type = FillType.SOLID
    slide.background.fill_format.solid_fill_color.color = Color.red
    assert slide.background.type == BackgroundType.OWN_BACKGROUND

    # Switch to themed
    slide.background.type = BackgroundType.THEMED
    assert slide.background.type == BackgroundType.THEMED
    slide.background.style_index = 5

    pres2 = tmp_pptx(pres)
    bg = pres2.slides[0].background
    assert bg.type == BackgroundType.THEMED
    assert bg.style_index == 5
    pres2.dispose()