TEST(CellDataUnitTests, blank_cells_are_blank_by_default)
{
    Workbook workbook;
    auto cell = workbook.GetWorksheets()[0].GetCells()["Z99"];

    EXPECT_EQ(CellValueType::Blank, cell.GetType());
    EXPECT_TRUE(cell.GetValue().IsEmpty());
    EXPECT_EQ("", cell.GetStringValue());
}