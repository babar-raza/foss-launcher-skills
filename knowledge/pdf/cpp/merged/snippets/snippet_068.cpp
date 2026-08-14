TEST(BmpEncoderSmoke, Bgra_2x2_HeaderAndBitfields) {
    auto pixels = Make2x2();
    foundation::bmp_encoder::Options opts;
    opts.color_type = foundation::bmp_encoder::ColorType::Bgra;
    const auto out = foundation::bmp_encoder::Encode(
        2, 2, std::span<const std::byte>(pixels), opts);

    // 14 + 40 + 12 (bitfields) + 2 * 2 * 4 = 66 + 16 = 82.
    ASSERT_EQ(out.size(), 82u);

    // bfOffBits = 14 + 40 + 12 = 66.
    EXPECT_EQ(Read32LE(out, 10), 66u);

    // biBitCount / biCompression.
    EXPECT_EQ(Read16LE(out, 28), 32u);
    EXPECT_EQ(Read32LE(out, 30), 3u);  // BI_BITFIELDS

    // BITFIELDS block at 54..65.
    EXPECT_EQ(Read32LE(out, 54), 0x00FF0000u);  // RedMask
    EXPECT_EQ(Read32LE(out, 58), 0x0000FF00u);  // GreenMask
    EXPECT_EQ(Read32LE(out, 62), 0x000000FFu);  // BlueMask
}