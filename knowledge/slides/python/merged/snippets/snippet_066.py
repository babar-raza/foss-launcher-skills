def test_solid_background_on_layout(tmp_pptx):
    """Solid-colour background on layout slide round-trips."""
    pres = Presentation()
    layout = pres.slides[0].layout_slide
    layout.background.type = BackgroundType.OWN_BACKGROUND
    layout.background.fill_format.fill_type = FillType.SOLID
    layout.background.fill_format.solid_fill_color.color = Color.coral

    pres2 = tmp_pptx(pres)
    bg = pres2.slides[0].layout_slide.background
    assert bg.type == BackgroundType.OWN_BACKGROUND
    assert bg.fill_format.fill_type == FillType.SOLID
    c = bg.fill_format.solid_fill_color.color
    assert c.r == 255 and c.g == 127 and c.b == 80
    pres2.dispose()