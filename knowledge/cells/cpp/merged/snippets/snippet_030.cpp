TEST(OpenXmlFeatureGoldenTests, worksheet_settings_roundtrip_and_emit_expected_markup)
{
    TempDir temp("golden-worksheet-settings");
    const auto path = temp.Path("worksheet-settings.xlsx");
    auto workbook = CreateWorksheetSettingsWorkbook();
    workbook.Save(path.string());

    const auto worksheetXml = Package::ReadEntryText(path, "xl/worksheets/sheet1.xml");
    const auto workbookXml = Package::ReadEntryText(path, "xl/workbook.xml");
    EXPECT_TRUE(Contains(worksheetXml, "dimension ref=\"A1:C4\""));
    EXPECT_TRUE(Contains(worksheetXml, "mergeCell ref=\"A1:B2\""));
    EXPECT_TRUE(Contains(worksheetXml, "hidden=\"1\""));
    EXPECT_TRUE(Contains(workbookXml, "state=\"hidden\""));

    Workbook loaded(path.string());
    AssertWorksheetSettings(loaded);
    AssertWorksheetSettingsScenarioHasVisibleSheet(loaded);
}