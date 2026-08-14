TEST(BorderInfoSmoke, DefaultHasNoEdges) {
    BorderInfo b;
    EXPECT_FLOAT_EQ(b.Left().LineWidth(), 0.0f);
    EXPECT_FLOAT_EQ(b.Top().LineWidth(), 0.0f);
    EXPECT_DOUBLE_EQ(b.RoundedBorderRadius(), 0.0);
}