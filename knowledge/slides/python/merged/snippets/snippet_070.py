def test_picture_background_stretch(tmp_pptx):
    """Picture background in stretch mode round-trips."""
    pres = Presentation()
    slide = pres.slides[0]

    slide.background.type = BackgroundType.OWN_BACKGROUND
    slide.background.fill_format.fill_type = FillType.PICTURE
    slide.background.fill_format.picture_fill_format.picture_fill_mode = PictureFillMode.STRETCH

    png_bytes = create_test_png(0, 128, 0)
    pp_image = pres.images.add_image(png_bytes)
    slide.background.fill_format.picture_fill_format.picture.image = pp_image

    pres2 = tmp_pptx(pres)
    bg = pres2.slides[0].background
    assert bg.type == BackgroundType.OWN_BACKGROUND
    assert bg.fill_format.fill_type == FillType.PICTURE
    assert bg.fill_format.picture_fill_format.picture_fill_mode == PictureFillMode.STRETCH
    pres2.dispose()