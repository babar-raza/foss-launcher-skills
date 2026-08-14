TEST(BmpDecoderSmoke, RejectsBiBitCountUnsupported) {
    auto src = Make2x2Rgba(0xFF);
    foundation::bmp_encoder::Options opts;
    opts.color_type = foundation::bmp_encoder::ColorType::Bgr;
    auto encoded = foundation::bmp_encoder::Encode(
        2, 2, std::span<const std::byte>(src), opts);
    // Patch biBitCount at offset 28 from 24 → 16.
    encoded[28] = std::byte{16};
    encoded[29] = std::byte{0};
    EXPECT_THROW(foundation::bmp_decoder::Decode(
                     std::span<const std::byte>(encoded)),
                 std::runtime_error);
}