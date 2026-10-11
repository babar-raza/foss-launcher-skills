TEST(BmpDecoderSmoke, RejectsBadSignature) {
    // 70-byte BMP-shaped buffer but wrong signature.
    std::vector<std::byte> buf(70, std::byte{0});
    buf[0] = std::byte{'X'};
    buf[1] = std::byte{'Y'};
    EXPECT_THROW(foundation::bmp_decoder::Decode(
                     std::span<const std::byte>(buf)),
                 std::runtime_error);
}