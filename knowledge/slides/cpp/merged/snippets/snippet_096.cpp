TEST(AdjustValueTest, DefaultConstructedHasEmptyNameAndZeroValue) {
    AdjustValue adj;
    EXPECT_EQ(adj.name(), "");
    EXPECT_EQ(adj.raw_value(), 0);
    EXPECT_DOUBLE_EQ(adj.angle_value(), 0.0);
}