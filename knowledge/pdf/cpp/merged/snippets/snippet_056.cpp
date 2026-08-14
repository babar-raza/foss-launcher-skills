TEST(BmpDecoderSmoke, RejectsTopDownNegativeHeight) {
    auto src = Make2x2Rgba(0xFF);
    foundation::bmp_encoder::Options opts;
    opts.color_type = foundation::bmp_encoder::ColorType::Bgr;
    auto encoded = foundation::bmp_encoder::Encode(
        2, 2, std::span<const std::byte>(src), opts);
    // Flip biHeight to negative (offset 22..25 = -2 LE).
    encoded[22] = std::byte{0xFE};
    encoded[23] = std::byte{0xFF};
    encoded[24] = std::byte{0xFF};
    encoded[25] = std::byte{0xFF};
    EXPECT_THROW(foundation::bmp_decoder::Decode(
                     std::span<const std::byte>(encoded)),
                 std::runtime_error);
}