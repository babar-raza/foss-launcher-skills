TEST(CcittEncode, G3BlackIs1Polarity) {
    ExpectRoundTrip(MakeImage(40, 5, Checkerboard(40, 5, 5)), 0, true);
}