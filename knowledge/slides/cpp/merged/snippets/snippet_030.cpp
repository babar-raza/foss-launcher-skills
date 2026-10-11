TEST_F(ImagesIntegrationTest, MultipleImages) {
    Presentation pres;
    struct RGB { std::uint8_t r, g, b; };
    RGB colours[] = {{255, 0, 0}, {0, 255, 0}, {0, 0, 255}};
    for (auto [r, g, b] : colours) {
        auto png = create_test_png(r, g, b);
        pres.images().add_image(std::span<const std::uint8_t>(png));
    }
    EXPECT_GE(pres.images().size(), 3u);

    // Iterate to verify we can enumerate them.
    std::size_t count = 0;
    for ([[maybe_unused]] auto& img : pres.images()) {
        ++count;
    }
    EXPECT_GE(count, 3u);
}