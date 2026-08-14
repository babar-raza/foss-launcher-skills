TEST(BmpDecoderSmoke, Bgr_2x2_RoundtripsThroughEncoder) {
    auto src = Make2x2Rgba(0xFF);  // alpha=0xFF for BMP24 round-trip.
    foundation::bmp_encoder::Options opts;
    opts.color_type = foundation::bmp_encoder::ColorType::Bgr;
    const auto encoded = foundation::bmp_encoder::Encode(
        2, 2, std::span<const std::byte>(src), opts);

    const auto decoded = foundation::bmp_decoder::Decode(
        std::span<const std::byte>(encoded));
    EXPECT_EQ(decoded.width, 2u);
    EXPECT_EQ(decoded.height, 2u);
    EXPECT_EQ(decoded.components, 4u);
    EXPECT_EQ(decoded.pixels.size(), 16u);
    // BMP24 widens alpha to 0xFF on read; src has alpha=0xFF too →
    // byte-identical round-trip.
    EXPECT_EQ(decoded.pixels, src);
}