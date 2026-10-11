TEST(BmpDecoderSmoke, Bgr_3x4_OddWidthPadding) {
    constexpr std::uint32_t W = 3, H = 4;
    std::vector<std::byte> src(W * H * 4);
    // Pattern with byte distinct per pixel position.
    for (std::size_t i = 0; i < src.size(); i += 4) {
        src[i + 0] = std::byte{static_cast<std::uint8_t>(i)};
        src[i + 1] = std::byte{static_cast<std::uint8_t>(i + 1)};
        src[i + 2] = std::byte{static_cast<std::uint8_t>(i + 2)};
        src[i + 3] = std::byte{0xFF};  // alpha=0xFF for BMP24 round-trip.
    }
    foundation::bmp_encoder::Options opts;
    opts.color_type = foundation::bmp_encoder::ColorType::Bgr;
    const auto encoded = foundation::bmp_encoder::Encode(
        W, H, std::span<const std::byte>(src), opts);

    const auto decoded = foundation::bmp_decoder::Decode(
        std::span<const std::byte>(encoded));
    EXPECT_EQ(decoded.width, W);
    EXPECT_EQ(decoded.height, H);
    EXPECT_EQ(decoded.pixels, src);  // padding correctly skipped.
}