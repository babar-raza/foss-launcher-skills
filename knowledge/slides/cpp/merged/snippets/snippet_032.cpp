TEST_F(ImagesIntegrationTest, ImageFromFile) {
    // Determine path to test_data/lotus.png relative to the test binary.
    auto test_data = std::filesystem::path(__FILE__).parent_path().parent_path() / "test_data";
    auto img_path = test_data / "lotus.png";
    if (!std::filesystem::exists(img_path)) {
        GTEST_SKIP() << "lotus.png not in test_data";
    }

    // Read the file into a byte vector.
    std::ifstream file(img_path, std::ios::binary);
    ASSERT_TRUE(file.is_open());
    std::vector<std::uint8_t> file_data(
        (std::istreambuf_iterator<char>(file)),
        std::istreambuf_iterator<char>());

    Presentation pres;
    auto& pp_img = pres.images().add_image(
        std::span<const std::uint8_t>(file_data));
    pres.slides()[0].shapes().add_picture_frame(
        ShapeType::RECTANGLE, 50, 50, 200, 200, pp_img);
    EXPECT_GE(pres.slides()[0].shapes().size(), 1u);
}