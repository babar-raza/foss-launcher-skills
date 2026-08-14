TEST(CcittEncode, G4AllWhite) {
    auto img = MakeImage(8, 1, std::vector<bool>(8, false));
    ExpectRoundTrip(img, -1, false);
}