def test_gradient_background_with_stops(tmp_pptx):
    """Gradient background with colour stops round-trips."""
    pres = Presentation()
    slide = pres.slides[0]
    slide.background.type = BackgroundType.OWN_BACKGROUND
    slide.background.fill_format.fill_type = FillType.GRADIENT
    gf = slide.background.fill_format.gradient_format
    gf.gradient_shape = GradientShape.LINEAR
    gf.linear_gradient_angle = 90
    gf.gradient_stops.add(0.0, Color.red)
    gf.gradient_stops.add(1.0, Color.blue)

    pres2 = tmp_pptx(pres)
    bg = pres2.slides[0].background
    assert bg.fill_format.fill_type == FillType.GRADIENT
    stops = bg.fill_format.gradient_format.gradient_stops
    assert len(stops) >= 2
    pres2.dispose()