TEST(BmpDecoderSmoke, RejectsNonCanonicalBitfieldsMasks) {
    auto src = Make2x2Rgba(0xFF);
    foundation::bmp_encoder::Options opts;
    opts.color_type = foundation::bmp_encoder::ColorType::Bgra;
    auto encoded = foundation::bmp_encoder::Encode(
        2, 2, std::span<const std::byte>(src), opts);
    // Corrupt RedMask at offset 54 — change to 0x0000FF00 (wrong).
    encoded[54] = std::byte{0x00};
    encoded[55] = std::byte{0xFF};
    encoded[56] = std::byte{0x00};
    encoded[57] = std::byte{0x00};
    EXPECT_THROW(foundation::bmp_decoder::Decode(
                     std::span<const std::byte>(encoded)),
                 std::runtime_error);
}