TEST(AdjustValueTest, ConstructWithNameAndRawValue) {
    AdjustValue adj("adj1", 30000);
    EXPECT_EQ(adj.name(), "adj1");
    EXPECT_EQ(adj.raw_value(), 30000);
}