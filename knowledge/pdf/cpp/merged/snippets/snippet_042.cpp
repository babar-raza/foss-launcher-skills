TEST(MarginInfoSmoke, AccessorRoundtrip) {
    Aspose::Pdf::MarginInfo m;
    m.Left(10.0);
    m.Right(20.0);
    m.Top(30.0);
    m.Bottom(40.0);
    EXPECT_NEAR(m.Left(),   10.0, kEps);
    EXPECT_NEAR(m.Right(),  20.0, kEps);
    EXPECT_NEAR(m.Top(),    30.0, kEps);
    EXPECT_NEAR(m.Bottom(), 40.0, kEps);
}