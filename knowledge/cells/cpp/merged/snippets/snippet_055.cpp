TEST(CellDataUnitTests, formula_property_normalizes_and_preserves_cached_value)
{
    Workbook workbook;
    auto& sheet = workbook.GetWorksheets()[0];
    auto cell = sheet.GetCells()["C3"];

    cell.PutValue(20);
    cell.SetFormula("A1+B1");

    EXPECT_EQ(CellValueType::Formula, cell.GetType());
    EXPECT_EQ("=A1+B1", cell.GetFormula());
    EXPECT_EQ("20", cell.GetStringValue());
    EXPECT_EQ(20, cell.GetValue().AsInteger());
}