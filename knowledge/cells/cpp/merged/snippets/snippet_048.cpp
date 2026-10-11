TEST(CellDataUnitTests, put_value_overloads_assign_expected_types)
{
    Workbook workbook;
    auto& sheet = workbook.GetWorksheets()[0];
    const auto timestamp = DateTime(2024, 5, 6, 7, 8, 9);

    sheet.GetCells()["A1"].PutValue("alpha");
    sheet.GetCells()["B1"].PutValue(123);
    sheet.GetCells()["C1"].PutValue(12.5);
    sheet.GetCells()["D1"].PutValue(6.02214076E+23);
    sheet.GetCells()["E1"].PutValue(true);
    sheet.GetCells()["F1"].PutValue(timestamp);

    EXPECT_EQ(CellValueType::String, sheet.GetCells()["A1"].GetType());
    EXPECT_EQ(CellValueType::Number, sheet.GetCells()["B1"].GetType());
    EXPECT_EQ(CellValueType::Number, sheet.GetCells()["C1"].GetType());
    EXPECT_EQ(CellValueType::Number, sheet.GetCells()["D1"].GetType());
    EXPECT_EQ(CellValueType::Boolean, sheet.GetCells()["E1"].GetType());
    EXPECT_EQ(CellValueType::DateTime, sheet.GetCells()["F1"].GetType());

    EXPECT_EQ("alpha", sheet.GetCells()["A1"].GetValue().AsString());
    EXPECT_EQ(123, sheet.GetCells()["B1"].GetValue().AsInteger());
    EXPECT_DOUBLE_EQ(12.5, sheet.GetCells()["C1"].GetValue().AsDouble());
    EXPECT_LT(std::abs(sheet.GetCells()["D1"].GetValue().AsDouble() - 6.02214076E+23), 1E+10);
    EXPECT_TRUE(sheet.GetCells()["E1"].GetValue().AsBool());
    EXPECT_EQ(timestamp, sheet.GetCells()["F1"].GetValue().AsDateTime());
}