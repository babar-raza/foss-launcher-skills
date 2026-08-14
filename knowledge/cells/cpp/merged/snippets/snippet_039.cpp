TEST(OpenXmlFeatureGoldenTests, conditional_formattings_roundtrip_and_emit_expected_markup)
{
    TempDir temp("golden-conditional-formatting");
    const auto path = temp.Path("conditional-formatting.xlsx");
    auto workbook = CreateConditionalFormattingWorkbook();
    workbook.Save(path.string());

    const auto worksheetXml = Package::ReadEntryText(path, "xl/worksheets/sheet1.xml");
    const auto stylesXml = Package::ReadEntryText(path, "xl/styles.xml");
    EXPECT_TRUE(Contains(worksheetXml, "<conditionalFormatting"));
    EXPECT_TRUE(Contains(worksheetXml, "type=\"cellIs\""));
    EXPECT_TRUE(Contains(worksheetXml, "type=\"expression\""));
    EXPECT_TRUE(Contains(worksheetXml, "operator=\"between\""));
    EXPECT_TRUE(Contains(worksheetXml, "stopIfTrue=\"1\""));
    EXPECT_TRUE(Contains(worksheetXml, "<formula>MOD(A1,2)=0</formula>"));
    EXPECT_TRUE(Contains(stylesXml, "<dxfs"));
    EXPECT_TRUE(Contains(stylesXml, "count=\"3\""));

    Workbook loaded(path.string());
    AssertConditionalFormattings(loaded);
}