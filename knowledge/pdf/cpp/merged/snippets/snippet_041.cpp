TEST(MarginInfoSmoke, ParamCtorSetsAllFour) {
    // Canonical ctor parameter order is (left, bottom, right, top).
    Aspose::Pdf::MarginInfo m{1.0, 2.0, 3.0, 4.0};
    EXPECT_NEAR(m.Left(),   1.0, kEps);
    EXPECT_NEAR(m.Bottom(), 2.0, kEps);
    EXPECT_NEAR(m.Right(),  3.0, kEps);
    EXPECT_NEAR(m.Top(),    4.0, kEps);
}