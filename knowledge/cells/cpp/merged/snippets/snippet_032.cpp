TEST(OpenXmlFeatureGoldenTests, worksheet_protection_roundtrip_and_emit_expected_markup)
{
    TempDir temp("golden-worksheet-protection");
    const auto path = temp.Path("worksheet-protection.xlsx");
    auto workbook = CreateWorksheetSettingsWorkbook();
    workbook.Save(path.string());

    const auto worksheetXml = Package::ReadEntryText(path, "xl/worksheets/sheet1.xml");
    EXPECT_TRUE(Contains(worksheetXml, "<sheetProtection"));
    EXPECT_TRUE(Contains(worksheetXml, "sheet=\"1\""));
    EXPECT_TRUE(Contains(worksheetXml, "objects=\"1\""));
    EXPECT_TRUE(Contains(worksheetXml, "scenarios=\"1\""));
    EXPECT_TRUE(Contains(worksheetXml, "formatCells=\"1\""));
    EXPECT_TRUE(Contains(worksheetXml, "insertRows=\"1\""));
    EXPECT_TRUE(Contains(worksheetXml, "autoFilter=\"1\""));
    EXPECT_TRUE(Contains(worksheetXml, "selectLockedCells=\"1\""));
    EXPECT_TRUE(Contains(worksheetXml, "selectUnlockedCells=\"1\""));

    Workbook loaded(path.string());
    AssertWorksheetSettings(loaded);
    AssertWorksheetSettingsScenarioHasVisibleSheet(loaded);
}