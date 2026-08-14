TEST_F(ImagesIntegrationTest, PictureFrame) {
    Presentation pres;
    auto png = create_test_png(0, 0, 255);
    auto& img = pres.images().add_image(std::span<const std::uint8_t>(png));
    pres.slides()[0].shapes().add_picture_frame(
        ShapeType::RECTANGLE, 50, 50, 100, 100, img);
    EXPECT_GE(pres.slides()[0].shapes().size(), 1u);

    auto pres2 = save_and_reopen(pres);
    EXPECT_GE(pres2.slides()[0].shapes().size(), 1u);
}