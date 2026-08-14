TEST(BmpEncoderSmoke, Bgr_3x4_RowPaddingThreeBytes) {
    // 3 px wide, BMP24 → row data = 9 bytes, padding to 12.
    constexpr std::uint32_t W = 3, H = 4;
    std::vector<std::byte> pixels(W * H * 4, std::byte{0});
    foundation::bmp_encoder::Options opts;
    opts.color_type = foundation::bmp_encoder::ColorType::Bgr;
    const auto out = foundation::bmp_encoder::Encode(
        W, H, std::span<const std::byte>(pixels), opts);

    // 14 + 40 + 4 rows * 12 stride = 54 + 48 = 102.
    EXPECT_EQ(out.size(), 102u);
    // biSizeImage at offset 34 = 48.
    EXPECT_EQ(Read32LE(out, 34), 48u);
}