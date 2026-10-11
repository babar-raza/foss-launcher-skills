TEST(OpenXmlFeatureGoldenTests, hyperlinks_roundtrip_and_emit_expected_markup)
{
    TempDir temp("golden-hyperlinks");
    const auto path = temp.Path("hyperlinks.xlsx");
    auto workbook = CreateHyperlinkWorkbook();
    workbook.Save(path.string());

    const auto worksheetXml = Package::ReadEntryText(path, "xl/worksheets/sheet1.xml");
    const auto relsXml = Package::ReadEntryText(path, "xl/worksheets/_rels/sheet1.xml.rels");
    EXPECT_TRUE(Contains(worksheetXml, "<hyperlinks>"));
    EXPECT_TRUE(Contains(worksheetXml, "ref=\"A1\""));
    EXPECT_TRUE(Contains(worksheetXml, "location=\"'Target Sheet'!C3\""));
    EXPECT_TRUE(Contains(relsXml, "Target=\"https://example.com/docs?q=1\""));
    EXPECT_TRUE(Contains(relsXml, "Target=\"mailto:test@example.com\""));

    Workbook loaded(path.string());
    AssertHyperlinks(loaded);
}