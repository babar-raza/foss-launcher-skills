TEST(CcittEncode, G4Checkerboard64) {
    auto img = MakeImage(64, 64, Checkerboard(64, 64, 8));
    ExpectRoundTrip(img, -1, false);
}