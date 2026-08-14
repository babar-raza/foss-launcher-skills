TEST(AdjustValueTest, SetRawValue) {
    AdjustValue adj("adj1", 0);
    adj.set_raw_value(50000);
    EXPECT_EQ(adj.raw_value(), 50000);
}