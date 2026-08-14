TEST(BmpEncoderSmoke, RejectsUnknownColorType) {
    std::vector<std::byte> pixels(16, std::byte{0});
    foundation::bmp_encoder::Options opts;
    opts.color_type = static_cast<foundation::bmp_encoder::ColorType>(99);
    EXPECT_THROW(
        foundation::bmp_encoder::Encode(
            2, 2, std::span<const std::byte>(pixels), opts),
        std::runtime_error);
}