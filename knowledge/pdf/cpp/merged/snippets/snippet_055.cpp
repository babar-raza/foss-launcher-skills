TEST(BmpDecoderSmoke, RejectsBiSizeMismatch) {
    auto src = Make2x2Rgba(0xFF);
    foundation::bmp_encoder::Options opts;
    opts.color_type = foundation::bmp_encoder::ColorType::Bgr;
    auto encoded = foundation::bmp_encoder::Encode(
        2, 2, std::span<const std::byte>(src), opts);
    // Corrupt biSize at offset 14 — set to 12 (BITMAPCOREHEADER).
    encoded[14] = std::byte{12};
    EXPECT_THROW(foundation::bmp_decoder::Decode(
                     std::span<const std::byte>(encoded)),
                 std::runtime_error);
}