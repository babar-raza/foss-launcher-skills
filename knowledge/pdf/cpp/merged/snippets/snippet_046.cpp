TEST(BaseParagraphSmoke, DefaultAccessors) {
    Para p;
    EXPECT_EQ(p.VerticalAlignment(),
              Aspose::Pdf::VerticalAlignment::None);
    EXPECT_EQ(p.HorizontalAlignment(),
              Aspose::Pdf::HorizontalAlignment::None);
    EXPECT_FALSE(p.IsFirstParagraphInColumn());
    EXPECT_FALSE(p.IsKeptWithNext());
    EXPECT_FALSE(p.IsInNewPage());
    EXPECT_FALSE(p.IsInLineParagraph());
    EXPECT_EQ(p.ZIndex(), 0);
    EXPECT_EQ(p.Hyperlink(), nullptr);
    EXPECT_NEAR(p.Margin().Left(), 0.0, kEps);
}