TEST(BmpDecoderSmoke, RejectsTruncatedPixelData) {
    auto src = Make2x2Rgba(0xFF);
    foundation::bmp_encoder::Options opts;
    opts.color_type = foundation::bmp_encoder::ColorType::Bgr;
    auto encoded = foundation::bmp_encoder::Encode(
        2, 2, std::span<const std::byte>(src), opts);
    // Drop the last 4 bytes so the declared pixel data runs past EOF.
    encoded.resize(encoded.size() - 4);
    EXPECT_THROW(foundation::bmp_decoder::Decode(
                     std::span<const std::byte>(encoded)),
                 std::runtime_error);
}