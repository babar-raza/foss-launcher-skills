TEST(BmpDecoderSmoke, Bgra_2x2_RoundtripPreservesAlpha) {
    // Non-trivial alpha values to verify preservation.
    std::vector<std::byte> src;
    auto push = [&](std::uint8_t r, std::uint8_t g, std::uint8_t b,
                    std::uint8_t a) {
        src.push_back(std::byte{r});
        src.push_back(std::byte{g});
        src.push_back(std::byte{b});
        src.push_back(std::byte{a});
    };
    push(0x10, 0x20, 0x30, 0x40);
    push(0x50, 0x60, 0x70, 0x80);
    push(0x90, 0xA0, 0xB0, 0xC0);
    push(0xD0, 0xE0, 0xF0, 0xFF);

    foundation::bmp_encoder::Options opts;
    opts.color_type = foundation::bmp_encoder::ColorType::Bgra;
    const auto encoded = foundation::bmp_encoder::Encode(
        2, 2, std::span<const std::byte>(src), opts);

    const auto decoded = foundation::bmp_decoder::Decode(
        std::span<const std::byte>(encoded));
    EXPECT_EQ(decoded.width, 2u);
    EXPECT_EQ(decoded.height, 2u);
    EXPECT_EQ(decoded.pixels, src);  // BMP32 pass-through round-trip.
}