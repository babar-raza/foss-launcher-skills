TEST(CellDataGoldenTests, shared_strings_export_uses_sst_when_enabled)
{
    TempDir temp("golden-sst");
    const auto path = temp.Path("shared-strings.xlsx");
    Workbook workbook;
    workbook.GetWorksheets()[0].GetCells()["A1"].PutValue("Hello");
    workbook.GetWorksheets()[0].GetCells()["A2"].PutValue("Hello");
    SaveOptions options;
    options.SetUseSharedStrings(true);
    workbook.Save(path.string(), options);

    EXPECT_TRUE(Package::EntryExists(path, "xl/sharedStrings.xml"));
    const auto sharedStringsXml = Package::ReadEntryText(path, "xl/sharedStrings.xml");
    const auto worksheetXml = Package::ReadEntryText(path, "xl/worksheets/sheet1.xml");

    EXPECT_TRUE(Contains(sharedStringsXml, "<sst"));
    EXPECT_TRUE(Contains(sharedStringsXml, "uniqueCount=\"1\""));
    EXPECT_TRUE(Contains(worksheetXml, "t=\"s\""));
}