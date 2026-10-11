TEST(BorderInfoSmoke, ConstructorsConfigureNamedEdges) {
    // All edges, explicit width + colour.
    BorderInfo all{BorderSide::All, 2.0f, Color::FromRgb(0.0, 0.0, 1.0)};
    EXPECT_FLOAT_EQ(all.Left().LineWidth(), 2.0f);
    EXPECT_FLOAT_EQ(all.Bottom().LineWidth(), 2.0f);
    EXPECT_DOUBLE_EQ(all.Right().Color().A(), 1.0);

    // Only the named sides are configured; the rest stay at width 0.
    BorderInfo lr{BorderSide::Left | BorderSide::Right, 3.0f};
    EXPECT_FLOAT_EQ(lr.Left().LineWidth(), 3.0f);
    EXPECT_FLOAT_EQ(lr.Right().LineWidth(), 3.0f);
    EXPECT_FLOAT_EQ(lr.Top().LineWidth(), 0.0f);
    EXPECT_FLOAT_EQ(lr.Bottom().LineWidth(), 0.0f);

    // GraphInfo-valued constructor.
    GraphInfo g;
    g.LineWidth(5.0f);
    BorderInfo top{BorderSide::Top, g};
    EXPECT_FLOAT_EQ(top.Top().LineWidth(), 5.0f);
    EXPECT_FLOAT_EQ(top.Left().LineWidth(), 0.0f);

    top.RoundedBorderRadius(4.0);
    EXPECT_DOUBLE_EQ(top.RoundedBorderRadius(), 4.0);
}