TEST(CellDataGoldenTests, inline_strings_export_when_shared_strings_disabled)
{
    TempDir temp("golden-inline");
    const auto path = temp.Path("inline.xlsx");
    Workbook workbook;
    workbook.GetWorksheets()[0].GetCells()["A1"].PutValue("Inline");
    SaveOptions options;
    options.SetUseSharedStrings(false);
    workbook.Save(path.string(), options);

    EXPECT_FALSE(Package::EntryExists(path, "xl/sharedStrings.xml"));
    const auto worksheetXml = Package::ReadEntryText(path, "xl/worksheets/sheet1.xml");
    EXPECT_TRUE(Contains(worksheetXml, "t=\"inlineStr\""));
    EXPECT_TRUE(Contains(worksheetXml, "<t>Inline</t>"));
}