TEST(GraphInfoSmoke, Properties) {
    GraphInfo g;
    EXPECT_FLOAT_EQ(g.LineWidth(), 1.0f);
    EXPECT_DOUBLE_EQ(g.ScalingRateX(), 1.0);
    EXPECT_FALSE(g.IsDoubled());
    EXPECT_TRUE(g.DashArray().empty());

    g.LineWidth(2.5f);
    g.Color(Color::FromRgb(1.0, 0.0, 0.0));
    g.DashArray({3, 2});
    g.DashPhase(1);
    g.IsDoubled(true);
    g.RotationAngle(45.0);

    EXPECT_FLOAT_EQ(g.LineWidth(), 2.5f);
    EXPECT_DOUBLE_EQ(g.Color().A(), 1.0);
    ASSERT_EQ(g.DashArray().size(), 2u);
    EXPECT_EQ(g.DashArray()[0], 3);
    EXPECT_EQ(g.DashPhase(), 1);
    EXPECT_TRUE(g.IsDoubled());
    EXPECT_DOUBLE_EQ(g.RotationAngle(), 45.0);
}