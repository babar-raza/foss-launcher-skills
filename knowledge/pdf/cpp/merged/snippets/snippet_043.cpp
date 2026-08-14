TEST(VerticalAlignmentEnum, CanonicalValues) {
    using Aspose::Pdf::VerticalAlignment;
    EXPECT_EQ(static_cast<int>(VerticalAlignment::None),   0);
    EXPECT_EQ(static_cast<int>(VerticalAlignment::Top),    1);
    EXPECT_EQ(static_cast<int>(VerticalAlignment::Center), 2);
    EXPECT_EQ(static_cast<int>(VerticalAlignment::Bottom), 3);
}