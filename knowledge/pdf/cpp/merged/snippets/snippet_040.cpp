TEST(MarginInfoSmoke, DefaultConstructedIsZero) {
    Aspose::Pdf::MarginInfo m;
    EXPECT_NEAR(m.Left(),   0.0, kEps);
    EXPECT_NEAR(m.Right(),  0.0, kEps);
    EXPECT_NEAR(m.Top(),    0.0, kEps);
    EXPECT_NEAR(m.Bottom(), 0.0, kEps);
}