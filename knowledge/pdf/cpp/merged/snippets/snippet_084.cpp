TEST(CcittEncode, G4SingleRowHalfWhiteHalfBlack) {
    std::vector<bool> px(16, false);
    for (int c = 8; c < 16; ++c) px[c] = true;  // 8 white then 8 black
    ExpectRoundTrip(MakeImage(16, 1, px), -1, false);
}