def test_gradient_background(tmp_pptx):
    """Gradient background with tile flip round-trips."""
    pres = Presentation()
    slide = pres.slides[0]
    slide.background.type = BackgroundType.OWN_BACKGROUND
    slide.background.fill_format.fill_type = FillType.GRADIENT
    slide.background.fill_format.gradient_format.tile_flip = TileFlip.FLIP_BOTH

    pres2 = tmp_pptx(pres)
    bg = pres2.slides[0].background
    assert bg.type == BackgroundType.OWN_BACKGROUND
    assert bg.fill_format.fill_type == FillType.GRADIENT
    assert bg.fill_format.gradient_format.tile_flip == TileFlip.FLIP_BOTH
    pres2.dispose()