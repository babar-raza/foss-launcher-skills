TEST(OpenXmlFeatureGoldenTests, page_setup_roundtrip_and_emit_expected_markup)
{
    TempDir temp("golden-page-setup");
    const auto path = temp.Path("page-setup.xlsx");
    auto workbook = CreatePageSetupWorkbook();
    workbook.Save(path.string());

    const auto worksheetXml = Package::ReadEntryText(path, "xl/worksheets/sheet1.xml");
    EXPECT_TRUE(Contains(worksheetXml, "pageMargins"));
    EXPECT_TRUE(Contains(worksheetXml, "pageSetup"));
    EXPECT_TRUE(Contains(worksheetXml, "orientation=\"landscape\""));
    EXPECT_TRUE(Contains(worksheetXml, "paperSize=\"9\""));
    EXPECT_TRUE(Contains(worksheetXml, "<rowBreaks"));
    EXPECT_TRUE(Contains(worksheetXml, "<colBreaks"));

    Workbook loaded(path.string());
    AssertPageSetup(loaded);
}