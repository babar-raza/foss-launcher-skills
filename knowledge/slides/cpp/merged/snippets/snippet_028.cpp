TEST_F(FillFormatIntegrationTest, PictureFill) {
    Presentation pres;
    auto& slide = clear_slide(pres);
    auto& shape = slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 50, 50, 200, 200);
    shape.fill_format().set_fill_type(FillType::PICTURE);
    auto& pff = shape.fill_format().picture_fill_format();
    pff.set_picture_fill_mode(PictureFillMode::STRETCH);
    auto png = create_test_png(0, 255, 0);
    auto& img = pres.images().add_image(
        std::span<const uint8_t>(png.data(), png.size()));
    pff.picture().set_image(&img);

    auto pres2 = save_and_reopen(pres);
    auto& ff2 = pres2.slides()[0].shapes()[0].fill_format();
    EXPECT_EQ(ff2.fill_type(), FillType::PICTURE);
}