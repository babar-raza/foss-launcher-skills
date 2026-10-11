TEST(CcittEncode, G4BlackIs1Polarity) {
    auto img = MakeImage(32, 4, Checkerboard(32, 4, 4));
    ExpectRoundTrip(img, -1, true);
}