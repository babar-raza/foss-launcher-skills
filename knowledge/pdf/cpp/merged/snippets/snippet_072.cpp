TEST(BmpEncoderSmoke, RejectsZeroDimensions) {
    std::vector<std::byte> empty;
    foundation::bmp_encoder::Options opts;
    EXPECT_THROW(
        foundation::bmp_encoder::Encode(
            0, 1, std::span<const std::byte>(empty), opts),
        std::runtime_error);
    EXPECT_THROW(
        foundation::bmp_encoder::Encode(
            1, 0, std::span<const std::byte>(empty), opts),
        std::runtime_error);
}