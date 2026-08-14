TEST(AdjustValueTest, AngleValueConversion) {
    AdjustValue adj("adj1", 60000);
    EXPECT_DOUBLE_EQ(adj.angle_value(), 1.0);

    adj.set_raw_value(180000);
    EXPECT_DOUBLE_EQ(adj.angle_value(), 3.0);
}