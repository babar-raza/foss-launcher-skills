TEST(WorkbookPortingTests, CellValuesAndFormulaRoundTripThroughFacade)
{
    Workbook workbook;
    PopulateBasicWorkbook(workbook);
    auto& cells = workbook.GetWorksheets()[0].GetCells();

    EXPECT_EQ(CellValueType::String, cells["A1"].GetType());
    EXPECT_EQ("alpha", cells["A1"].GetValue().AsString());
    EXPECT_EQ(CellValueType::Number, cells["B1"].GetType());
    EXPECT_EQ(42, cells["B1"].GetValue().AsInteger());
    EXPECT_EQ(CellValueType::Boolean, cells["C1"].GetType());
    EXPECT_TRUE(cells["C1"].GetValue().AsBool());
    EXPECT_EQ(CellValueType::DateTime, cells["D1"].GetType());
    EXPECT_EQ(DateTime(2024, 5, 6, 7, 8, 9), cells["D1"].GetValue().AsDateTime());
    EXPECT_EQ(CellValueType::Formula, cells["E1"].GetType());
    EXPECT_EQ("=B1*2", cells["E1"].GetFormula());
    EXPECT_EQ(21, cells["E1"].GetValue().AsInteger());
}