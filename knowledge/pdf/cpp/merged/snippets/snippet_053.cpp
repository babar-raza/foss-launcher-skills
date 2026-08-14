TEST(BmpDecoderSmoke, RejectsTooShort) {
    std::vector<std::byte> tiny(3, std::byte{0});
    EXPECT_THROW(foundation::bmp_decoder::Decode(
                     std::span<const std::byte>(tiny)),
                 std::runtime_error);
}