TEST(OpenXmlFeatureGoldenTests, autofilter_roundtrip_and_emit_expected_markup)
{
    TempDir temp("golden-autofilter");
    const auto path = temp.Path("autofilter.xlsx");
    auto workbook = CreateAutoFilterWorkbook();
    workbook.Save(path.string());

    const auto worksheetXml = Package::ReadEntryText(path, "xl/worksheets/sheet1.xml");
    const auto workbookXml = Package::ReadEntryText(path, "xl/workbook.xml");
    EXPECT_TRUE(Contains(worksheetXml, "<autoFilter ref=\"A1:E6\""));
    EXPECT_TRUE(Contains(worksheetXml, "<filterColumn colId=\"0\" hiddenButton=\"1\">"));
    EXPECT_TRUE(Contains(worksheetXml, "<filters><filter val=\"Open\" /><filter val=\"Closed\" /></filters>"));
    EXPECT_TRUE(Contains(worksheetXml, "<customFilters and=\"1\">"));
    EXPECT_TRUE(Contains(worksheetXml, "operator=\"greaterThanOrEqual\""));
    EXPECT_TRUE(Contains(worksheetXml, "operator=\"lessThanOrEqual\""));
    EXPECT_TRUE(Contains(worksheetXml, "<colorFilter dxfId=\"3\" cellColor=\"1\" />"));
    EXPECT_TRUE(Contains(worksheetXml, "<dynamicFilter type=\"thisMonth\" val=\"1\" maxVal=\"31\" />"));
    EXPECT_TRUE(Contains(worksheetXml, "<top10 top=\"0\" percent=\"1\" val=\"10\" filterVal=\"2.5\" />"));
    EXPECT_TRUE(Contains(worksheetXml, "<sortState ref=\"A2:E6\" caseSensitive=\"1\" sortMethod=\"pinYin\">"));
    EXPECT_TRUE(Contains(worksheetXml, "<sortCondition ref=\"B2:B6\" descending=\"1\" sortBy=\"value\" customList=\"High,Medium,Low\" />"));
    EXPECT_TRUE(Contains(worksheetXml, "<sortCondition ref=\"C2:C6\" sortBy=\"cellColor\" dxfId=\"4\" />"));
    EXPECT_TRUE(Contains(worksheetXml, "<sortCondition ref=\"E2:E6\" sortBy=\"icon\" iconSet=\"3TrafficLights1\" iconId=\"2\" />"));
    EXPECT_TRUE(Contains(workbookXml, "name=\"_xlnm._FilterDatabase\""));
    EXPECT_TRUE(Contains(workbookXml, "'Filtered'!$A$1:$E$6"));

    Workbook loaded(path.string());
    AssertAutoFilter(loaded);
}