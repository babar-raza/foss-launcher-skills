def test_picture_background_tile(tmp_pptx):
    """Picture background in tile mode round-trips."""
    pres = Presentation()
    slide = pres.slides[0]

    slide.background.type = BackgroundType.OWN_BACKGROUND
    slide.background.fill_format.fill_type = FillType.PICTURE

    png_bytes = create_test_png(255, 0, 0)
    pp_image = pres.images.add_image(png_bytes)
    pff = slide.background.fill_format.picture_fill_format
    pff.picture.image = pp_image
    pff.picture_fill_mode = PictureFillMode.TILE

    pres2 = tmp_pptx(pres)
    bg = pres2.slides[0].background
    assert bg.fill_format.fill_type == FillType.PICTURE
    assert bg.fill_format.picture_fill_format.picture_fill_mode == PictureFillMode.TILE
    pres2.dispose()