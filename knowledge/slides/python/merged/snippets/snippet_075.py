def test_effective_own_background():
    """get_effective returns fill data for OWN_BACKGROUND slide."""
    pres = Presentation()
    slide = pres.slides[0]
    slide.background.type = BackgroundType.OWN_BACKGROUND
    slide.background.fill_format.fill_type = FillType.SOLID
    slide.background.fill_format.solid_fill_color.color = Color.coral

    eff = slide.background.get_effective()
    assert eff.fill_format.fill_type == FillType.SOLID
    c = eff.fill_format.solid_fill_color
    assert c.r == 255 and c.g == 127 and c.b == 80
    pres.dispose()