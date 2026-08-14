TEST(CcittEncode, RejectsKGreaterThanZero) {
    auto img = MakeImage(8, 1, std::vector<bool>(8, false));
    Params ep;
    ep.K = 2;
    ep.Columns = 8;
    ep.Rows = 1;
    EXPECT_THROW(Encode(img, ep), std::runtime_error);
}