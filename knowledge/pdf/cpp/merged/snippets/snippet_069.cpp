TEST(BmpEncoderSmoke, Bgra_2x2_AlphaPreserved) {
    // Build a 2x2 with non-trivial alpha values and verify the
    // BMP32 round-trip preserves them at offset +3.
    std::vector<std::byte> pixels;
    auto push = [&](std::uint8_t r, std::uint8_t g, std::uint8_t b,
                    std::uint8_t a) {
        pixels.push_back(std::byte{r});
        pixels.push_back(std::byte{g});
        pixels.push_back(std::byte{b});
        pixels.push_back(std::byte{a});
    };
    push(0x10, 0x20, 0x30, 0x40);
    push(0x50, 0x60, 0x70, 0x80);
    push(0x90, 0xA0, 0xB0, 0xC0);
    push(0xD0, 0xE0, 0xF0, 0xFF);

    foundation::bmp_encoder::Options opts;
    opts.color_type = foundation::bmp_encoder::ColorType::Bgra;
    const auto out = foundation::bmp_encoder::Encode(
        2, 2, std::span<const std::byte>(pixels), opts);

    // Pixel data at offset 66. Bottom-up: image-row 1 first.
    // image-row 1 is the second pair (0x90,A0,B0,C0) and (0xD0,E0,F0,FF).
    EXPECT_EQ(out[66], std::byte{0xB0});  // B
    EXPECT_EQ(out[67], std::byte{0xA0});  // G
    EXPECT_EQ(out[68], std::byte{0x90});  // R
    EXPECT_EQ(out[69], std::byte{0xC0});  // A — preserved
    EXPECT_EQ(out[70], std::byte{0xF0});
    EXPECT_EQ(out[71], std::byte{0xE0});
    EXPECT_EQ(out[72], std::byte{0xD0});
    EXPECT_EQ(out[73], std::byte{0xFF});
    // image-row 0 next: first pair (0x10,20,30,40) and (0x50,60,70,80).
    EXPECT_EQ(out[74], std::byte{0x30});
    EXPECT_EQ(out[75], std::byte{0x20});
    EXPECT_EQ(out[76], std::byte{0x10});
    EXPECT_EQ(out[77], std::byte{0x40});  // A
    EXPECT_EQ(out[78], std::byte{0x70});
    EXPECT_EQ(out[79], std::byte{0x60});
    EXPECT_EQ(out[80], std::byte{0x50});
    EXPECT_EQ(out[81], std::byte{0x80});  // A
}