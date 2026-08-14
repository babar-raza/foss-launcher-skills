def test_themed_background(tmp_pptx):
    """Themed background type and style_index round-trip."""
    pres = Presentation()
    slide = pres.slides[0]
    slide.background.type = BackgroundType.THEMED
    slide.background.style_index = 3

    pres2 = tmp_pptx(pres)
    bg = pres2.slides[0].background
    assert bg.type == BackgroundType.THEMED
    assert bg.style_index == 3
    pres2.dispose()