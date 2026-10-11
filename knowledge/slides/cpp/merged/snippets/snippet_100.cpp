TEST(AdjustValueTest, SetAngleValue) {
    AdjustValue adj;
    adj.set_angle_value(45.0);
    EXPECT_EQ(adj.raw_value(), 2700000);
    EXPECT_DOUBLE_EQ(adj.angle_value(), 45.0);
}