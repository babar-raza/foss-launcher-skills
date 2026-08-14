TEST(CcittEncode, RandomSweepRoundTrips) {
    std::mt19937 rng(1234);
    for (int K : {-1, 0}) {
        for (bool b1 : {false, true}) {
            for (int t = 0; t < 60; ++t) {
                const int cols = 1 + static_cast<int>(rng() % 300);
                const int rows = 1 + static_cast<int>(rng() % 16);
                std::vector<bool> px(static_cast<std::size_t>(cols) * rows);
                for (auto&& bit : px) bit = (rng() & 1) != 0;
                ExpectRoundTrip(MakeImage(cols, rows, px), K, b1);
            }
        }
    }
}