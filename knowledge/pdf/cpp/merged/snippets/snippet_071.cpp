TEST(BmpEncoderSmoke, Bgra_5x4_NoRowPadding) {
    // BMP32 always 4-aligned per row regardless of width.
    constexpr std::uint32_t W = 5, H = 4;
    std::vector<std::byte> pixels(W * H * 4, std::byte{0xAA});
    foundation::bmp_encoder::Options opts;
    opts.color_type = foundation::bmp_encoder::ColorType::Bgra;
    const auto out = foundation::bmp_encoder::Encode(
        W, H, std::span<const std::byte>(pixels), opts);

    // 14 + 40 + 12 + 4 rows * 5*4 stride = 66 + 80 = 146.
    EXPECT_EQ(out.size(), 146u);
    EXPECT_EQ(Read32LE(out, 34), 80u);  // biSizeImage
}