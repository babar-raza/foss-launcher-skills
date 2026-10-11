TEST(CcittEncode, G3Checkerboard) {
    ExpectRoundTrip(MakeImage(64, 16, Checkerboard(64, 16, 8)), 0, false);
}