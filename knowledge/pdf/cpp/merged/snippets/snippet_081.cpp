TEST(CcittEncode, G4Alternating) {
    std::vector<bool> px = {true, false, true, false,
                            true, false, true, false};
    ExpectRoundTrip(MakeImage(8, 1, px), -1, false);
}