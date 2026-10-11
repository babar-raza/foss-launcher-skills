TEST(BorderStyleEnum, CanonicalValues) {
    EXPECT_EQ(static_cast<int>(BorderStyle::Solid),     0);
    EXPECT_EQ(static_cast<int>(BorderStyle::Dashed),    1);
    EXPECT_EQ(static_cast<int>(BorderStyle::Beveled),   2);
    EXPECT_EQ(static_cast<int>(BorderStyle::Inset),     3);
    EXPECT_EQ(static_cast<int>(BorderStyle::Underline), 4);
}