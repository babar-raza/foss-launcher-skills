def test_pattern_background(tmp_pptx):
    """Pattern background round-trips."""
    pres = Presentation()
    slide = pres.slides[0]
    slide.background.type = BackgroundType.OWN_BACKGROUND
    slide.background.fill_format.fill_type = FillType.PATTERN
    pf = slide.background.fill_format.pattern_format
    pf.pattern_style = PatternStyle.PERCENT50
    pf.fore_color.color = Color.dark_blue
    pf.back_color.color = Color.white

    pres2 = tmp_pptx(pres)
    bg = pres2.slides[0].background
    assert bg.type == BackgroundType.OWN_BACKGROUND
    assert bg.fill_format.fill_type == FillType.PATTERN
    assert bg.fill_format.pattern_format.pattern_style == PatternStyle.PERCENT50
    pres2.dispose()