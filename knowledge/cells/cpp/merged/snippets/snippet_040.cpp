TEST(OpenXmlFeatureGoldenTests, advanced_conditional_formattings_roundtrip_and_emit_expected_markup)
{
    TempDir temp("golden-advanced-conditional-formatting");
    const auto path = temp.Path("advanced-conditional-formatting.xlsx");
    auto workbook = CreateAdvancedConditionalFormattingWorkbook();
    workbook.Save(path.string());

    const auto worksheetXml = Package::ReadEntryText(path, "xl/worksheets/sheet1.xml");
    EXPECT_TRUE(Contains(worksheetXml, "type=\"containsText\""));
    EXPECT_TRUE(Contains(worksheetXml, "type=\"notContainsText\""));
    EXPECT_TRUE(Contains(worksheetXml, "type=\"beginsWith\""));
    EXPECT_TRUE(Contains(worksheetXml, "type=\"endsWith\""));
    EXPECT_TRUE(Contains(worksheetXml, "type=\"timePeriod\""));
    EXPECT_TRUE(Contains(worksheetXml, "type=\"duplicateValues\""));
    EXPECT_TRUE(Contains(worksheetXml, "type=\"uniqueValues\""));
    EXPECT_TRUE(Contains(worksheetXml, "type=\"top10\""));
    EXPECT_TRUE(Contains(worksheetXml, "type=\"aboveAverage\""));
    EXPECT_TRUE(Contains(worksheetXml, "type=\"colorScale\""));
    EXPECT_TRUE(Contains(worksheetXml, "type=\"dataBar\""));
    EXPECT_TRUE(Contains(worksheetXml, "type=\"iconSet\""));
    EXPECT_TRUE(Contains(worksheetXml, "<colorScale>"));
    EXPECT_TRUE(Contains(worksheetXml, "<dataBar>"));
    EXPECT_TRUE(Contains(worksheetXml, "<iconSet iconSet=\"4Arrows\" reverse=\"1\" showValue=\"0\">"));

    Workbook loaded(path.string());
    AssertAdvancedConditionalFormattings(loaded);
}