TEST_F(ImagesIntegrationTest, AddImage) {
    Presentation pres;
    auto png = create_test_png(255, 0, 0);
    pres.images().add_image(std::span<const std::uint8_t>(png));
    EXPECT_GE(pres.images().size(), 1u);
}