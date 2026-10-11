TEST(BmpEncoderSmoke, Bgr_2x2_HeaderLayout) {
    auto pixels = Make2x2();
    foundation::bmp_encoder::Options opts;
    opts.color_type = foundation::bmp_encoder::ColorType::Bgr;
    const auto out = foundation::bmp_encoder::Encode(
        2, 2, std::span<const std::byte>(pixels), opts);

    // 14 + 40 + 2 rows * (2*3 + 2 padding) = 54 + 16 = 70.
    ASSERT_EQ(out.size(), 70u);

    // 'BM' magic.
    EXPECT_EQ(out[0], std::byte{'B'});
    EXPECT_EQ(out[1], std::byte{'M'});

    // bfSize equals total length.
    EXPECT_EQ(Read32LE(out, 2), 70u);
    // bfReserved1/2 = 0
    EXPECT_EQ(Read16LE(out, 6), 0u);
    EXPECT_EQ(Read16LE(out, 8), 0u);
    // bfOffBits = 14 + 40 = 54 (no BITFIELDS for BMP24).
    EXPECT_EQ(Read32LE(out, 10), 54u);

    // BITMAPINFOHEADER.
    EXPECT_EQ(Read32LE(out, 14), 40u);  // biSize
    EXPECT_EQ(Read32LESigned(out, 18), 2);  // biWidth
    EXPECT_EQ(Read32LESigned(out, 22), 2);  // biHeight (positive)
    EXPECT_EQ(Read16LE(out, 26), 1u);  // biPlanes
    EXPECT_EQ(Read16LE(out, 28), 24u);  // biBitCount
    EXPECT_EQ(Read32LE(out, 30), 0u);  // biCompression = BI_RGB
    EXPECT_EQ(Read32LE(out, 34), 16u);  // biSizeImage = 2 rows * 8 stride
    EXPECT_EQ(Read32LESigned(out, 38), 2835);  // biXPelsPerMeter
    EXPECT_EQ(Read32LESigned(out, 42), 2835);  // biYPelsPerMeter
    EXPECT_EQ(Read32LE(out, 46), 0u);  // biClrUsed
    EXPECT_EQ(Read32LE(out, 50), 0u);  // biClrImportant
}