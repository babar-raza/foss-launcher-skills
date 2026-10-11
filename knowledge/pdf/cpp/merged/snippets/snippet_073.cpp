TEST(BmpEncoderSmoke, RejectsBufferLengthMismatch) {
    std::vector<std::byte> too_small(15, std::byte{0});  // not 2*2*4=16
    foundation::bmp_encoder::Options opts;
    EXPECT_THROW(
        foundation::bmp_encoder::Encode(
            2, 2, std::span<const std::byte>(too_small), opts),
        std::runtime_error);
}