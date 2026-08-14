TEST(BmpEncoderSmoke, Bgr_2x2_PixelOrderAndPadding) {
    auto pixels = Make2x2();
    foundation::bmp_encoder::Options opts;
    opts.color_type = foundation::bmp_encoder::ColorType::Bgr;
    const auto out = foundation::bmp_encoder::Encode(
        2, 2, std::span<const std::byte>(pixels), opts);

    // Pixel data starts at offset 54. Bottom-up: file-row 0 is
    // image-row 1 (bottom), file-row 1 is image-row 0 (top).
    // Stride = 2*3 + 2 padding = 8.
    //
    // Image-row 1 (bottom): blue, white  →  B,G,R = 0xFF,0,0  /  0xFF,0xFF,0xFF
    EXPECT_EQ(out[54], std::byte{0xFF});  // B (blue's B)
    EXPECT_EQ(out[55], std::byte{0x00});  // G
    EXPECT_EQ(out[56], std::byte{0x00});  // R
    EXPECT_EQ(out[57], std::byte{0xFF});  // B (white)
    EXPECT_EQ(out[58], std::byte{0xFF});  // G
    EXPECT_EQ(out[59], std::byte{0xFF});  // R
    EXPECT_EQ(out[60], std::byte{0});  // padding
    EXPECT_EQ(out[61], std::byte{0});  // padding

    // Image-row 0 (top): red, green  →  B,G,R = 0,0,0xFF  /  0,0xFF,0
    EXPECT_EQ(out[62], std::byte{0x00});  // B
    EXPECT_EQ(out[63], std::byte{0x00});  // G
    EXPECT_EQ(out[64], std::byte{0xFF});  // R (red)
    EXPECT_EQ(out[65], std::byte{0x00});  // B
    EXPECT_EQ(out[66], std::byte{0xFF});  // G (green)
    EXPECT_EQ(out[67], std::byte{0x00});  // R
    EXPECT_EQ(out[68], std::byte{0});  // padding
    EXPECT_EQ(out[69], std::byte{0});  // padding
}