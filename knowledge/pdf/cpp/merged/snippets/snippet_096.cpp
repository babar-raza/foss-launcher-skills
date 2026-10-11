TEST(CellSmoke, Defaults) {
    Cell c;
    EXPECT_FALSE(c.IsNoBorder());
    EXPECT_EQ(c.ColSpan(), 1);
    EXPECT_EQ(c.RowSpan(), 1);
    EXPECT_TRUE(c.IsWordWrapped());
    EXPECT_EQ(c.Alignment(), HorizontalAlignment::Left);

    Cell sized{Rectangle{0.0, 0.0, 120.0, 40.0, false}};
    EXPECT_DOUBLE_EQ(sized.Width(), 120.0);
}