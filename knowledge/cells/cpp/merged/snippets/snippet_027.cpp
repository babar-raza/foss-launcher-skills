TEST(CellDataGoldenTests, mac1904_datetime_roundtrip_and_markup)
{
    TempDir temp("golden-1904");
    const auto path = temp.Path("date1904.xlsx");
    auto workbook = CreateMixedCellWorkbook(true);
    workbook.Save(path.string());

    const auto workbookXml = Package::ReadEntryText(path, "xl/workbook.xml");
    EXPECT_TRUE(Contains(workbookXml, "date1904=\"1\""));

    Workbook loaded(path.string());
    EXPECT_TRUE(loaded.GetSettings().GetDate1904());
    EXPECT_EQ(DateTime(2024, 5, 6, 7, 8, 9),
              loaded.GetWorksheets()[0].GetCells()["F1"].GetValue().AsDateTime());
}