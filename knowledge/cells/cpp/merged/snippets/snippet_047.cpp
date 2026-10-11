TEST(CellDataUnitTests, a1_indexers_roundtrip)
{
    Workbook workbook;
    auto& sheet = workbook.GetWorksheets()[0];
    sheet.GetCells()(2, 27).PutValue("AB3");
    sheet.GetCells()(0, 0).PutValue(42);

    EXPECT_EQ("AB3", sheet.GetCells()["AB3"].GetStringValue());
    EXPECT_EQ("42", sheet.GetCells()(0, 0).GetStringValue());
    EXPECT_EQ(CellValueType::String, sheet.GetCells()["AB3"].GetType());
    EXPECT_EQ(CellValueType::Number, sheet.GetCells()["A1"].GetType());
}