TEST(CcittEncode, G3AllBlack) {
    ExpectRoundTrip(MakeImage(8, 1, std::vector<bool>(8, true)), 0, false);
}