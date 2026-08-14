TEST(CcittEncode, G4LongRunsBeyond1728) {
    // A 2000-px-wide row exercises make-up + common make-up chaining.
    std::vector<bool> px(2000, false);
    for (int c = 1900; c < 2000; ++c) px[c] = true;
    ExpectRoundTrip(MakeImage(2000, 1, px), -1, false);
}