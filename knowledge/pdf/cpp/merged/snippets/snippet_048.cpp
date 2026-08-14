TEST(BaseParagraphSmoke, HyperlinkRoundtrip) {
    Para p;
    auto h = std::make_shared<Aspose::Pdf::Hyperlink>();
    p.Hyperlink(h);
    EXPECT_EQ(p.Hyperlink(), h);
}