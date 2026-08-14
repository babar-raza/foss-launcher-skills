TEST(BaseParagraphSmoke, AccessorRoundtrip) {
    Para p;
    p.VerticalAlignment(Aspose::Pdf::VerticalAlignment::Center);
    p.HorizontalAlignment(Aspose::Pdf::HorizontalAlignment::Right);
    p.IsFirstParagraphInColumn(true);
    p.IsKeptWithNext(true);
    p.IsInNewPage(true);
    p.IsInLineParagraph(true);
    p.ZIndex(7);
    p.Margin(Aspose::Pdf::MarginInfo{1.0, 2.0, 3.0, 4.0});

    EXPECT_EQ(p.VerticalAlignment(),
              Aspose::Pdf::VerticalAlignment::Center);
    EXPECT_EQ(p.HorizontalAlignment(),
              Aspose::Pdf::HorizontalAlignment::Right);
    EXPECT_TRUE(p.IsFirstParagraphInColumn());
    EXPECT_TRUE(p.IsKeptWithNext());
    EXPECT_TRUE(p.IsInNewPage());
    EXPECT_TRUE(p.IsInLineParagraph());
    EXPECT_EQ(p.ZIndex(), 7);
    EXPECT_NEAR(p.Margin().Left(),   1.0, kEps);
    EXPECT_NEAR(p.Margin().Bottom(), 2.0, kEps);
    EXPECT_NEAR(p.Margin().Right(),  3.0, kEps);
    EXPECT_NEAR(p.Margin().Top(),    4.0, kEps);
}