TEST(CcittEncode, G3AllWhite) {
    ExpectRoundTrip(MakeImage(8, 1, std::vector<bool>(8, false)), 0, false);
}