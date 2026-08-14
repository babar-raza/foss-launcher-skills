TEST(TextAlignmentEnum, CanonicalValues) {
    EXPECT_EQ(static_cast<int>(TextAlignment::Left),   0);
    EXPECT_EQ(static_cast<int>(TextAlignment::Center), 1);
    EXPECT_EQ(static_cast<int>(TextAlignment::Right),  2);
}