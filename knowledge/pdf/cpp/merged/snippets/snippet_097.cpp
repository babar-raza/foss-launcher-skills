TEST(CellSmoke, Properties) {
    Cell c;
    c.Border(BorderInfo{BorderSide::All, 1.5f});
    c.BackgroundColor(Color::FromRgb(0.9, 0.9, 0.9));
    c.Alignment(HorizontalAlignment::Center);
    c.ColSpan(2);
    c.RowSpan(3);
    c.IsNoBorder(true);

    EXPECT_FLOAT_EQ(c.Border().Top().LineWidth(), 1.5f);
    EXPECT_DOUBLE_EQ(c.BackgroundColor().A(), 1.0);
    EXPECT_EQ(c.Alignment(), HorizontalAlignment::Center);
    EXPECT_EQ(c.ColSpan(), 2);
    EXPECT_EQ(c.RowSpan(), 3);
    EXPECT_TRUE(c.IsNoBorder());
}