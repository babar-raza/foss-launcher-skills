TEST(WorkbookPortingTests, LoadXlsxFilePreservesCellsAndFormula)
{
    TempDir temp;
    const auto path = temp.Path("roundtrip.xlsx");

    Workbook workbook;
    PopulateBasicWorkbook(workbook);
    workbook.Save(path.string());

    Workbook loaded(path.string());
    auto& cells = loaded.GetWorksheets()["Data"].GetCells();

    EXPECT_EQ("alpha", cells["A1"].GetStringValue());
    EXPECT_EQ(42, cells["B1"].GetValue().AsInteger());
    EXPECT_TRUE(cells["C1"].GetValue().AsBool());
    EXPECT_EQ(DateTime(2024, 5, 6, 7, 8, 9), cells["D1"].GetValue().AsDateTime());
    EXPECT_EQ("=B1*2", cells["E1"].GetFormula());
    EXPECT_EQ(21, cells["E1"].GetValue().AsInteger());
}