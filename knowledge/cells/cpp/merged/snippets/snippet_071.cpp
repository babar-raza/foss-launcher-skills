TEST(WorkbookPortingTests, NewWorkbookHasDefaultWorksheetAndBlankCells)
{
    Workbook workbook;
    auto& sheets = workbook.GetWorksheets();

    ASSERT_EQ(1, sheets.GetCount());
    EXPECT_EQ("Sheet1", sheets[0].GetName());

    auto cell = sheets[0].GetCells()["Z99"];
    EXPECT_EQ(CellValueType::Blank, cell.GetType());
    EXPECT_TRUE(cell.GetValue().IsEmpty());
    EXPECT_EQ("", cell.GetStringValue());
}