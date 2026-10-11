TEST(CcittEncode, G4TwoIdenticalRows) {
    std::vector<bool> px = {true, true, false, false, true, true, false, false,
                            true, true, false, false, true, true, false, false};
    ExpectRoundTrip(MakeImage(8, 2, px), -1, false);
}