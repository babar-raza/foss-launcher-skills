TEST(OpenXmlFeatureGoldenTests, worksheet_view_and_tab_color_roundtrip_and_emit_expected_markup)
{
    TempDir temp("golden-worksheet-view");
    const auto path = temp.Path("worksheet-view.xlsx");
    auto workbook = CreateWorksheetSettingsWorkbook();
    workbook.Save(path.string());

    const auto worksheetXml = Package::ReadEntryText(path, "xl/worksheets/sheet1.xml");
    EXPECT_TRUE(Contains(worksheetXml, "<sheetViews>"));
    EXPECT_TRUE(Contains(worksheetXml, "showGridLines=\"0\""));
    EXPECT_TRUE(Contains(worksheetXml, "showRowColHeaders=\"0\""));
    EXPECT_TRUE(Contains(worksheetXml, "showZeros=\"0\""));
    EXPECT_TRUE(Contains(worksheetXml, "rightToLeft=\"1\""));
    EXPECT_TRUE(Contains(worksheetXml, "zoomScale=\"85\""));
    EXPECT_TRUE(Contains(worksheetXml, "tabColor rgb=\"FF224466\""));

    Workbook loaded(path.string());
    AssertWorksheetSettings(loaded);
    AssertWorksheetSettingsScenarioHasVisibleSheet(loaded);
}