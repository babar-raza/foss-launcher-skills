TEST(CcittEncode, G4AllBlack) {
    auto img = MakeImage(8, 1, std::vector<bool>(8, true));
    ExpectRoundTrip(img, -1, false);
}