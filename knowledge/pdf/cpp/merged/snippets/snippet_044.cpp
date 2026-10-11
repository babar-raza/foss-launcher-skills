TEST(HorizontalAlignmentEnum, CanonicalValues) {
    using Aspose::Pdf::HorizontalAlignment;
    EXPECT_EQ(static_cast<int>(HorizontalAlignment::None),        0);
    EXPECT_EQ(static_cast<int>(HorizontalAlignment::Left),        1);
    EXPECT_EQ(static_cast<int>(HorizontalAlignment::Center),      2);
    EXPECT_EQ(static_cast<int>(HorizontalAlignment::Right),       3);
    EXPECT_EQ(static_cast<int>(HorizontalAlignment::Justify),     4);
    EXPECT_EQ(static_cast<int>(HorizontalAlignment::FullJustify), 5);
}