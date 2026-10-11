TEST(CompatibilityTests, value_property_setter_matches_supported_scalar_behavior)
{
    Workbook workbook;
    auto& sheet = workbook.GetWorksheets()[0];
    sheet.GetCells()["A1"].SetValue("alpha");
    sheet.GetCells()["B1"].SetValue(12);
    sheet.GetCells()["C1"].SetValue(true);
    sheet.GetCells()["D1"].SetValue(DateTime(2024, 1, 2, 3, 4, 0));
    sheet.GetCells()["E1"].SetValue(CellValue());

    EXPECT_EQ("alpha", sheet.GetCells()["A1"].GetValue().AsString());
    EXPECT_EQ(12, sheet.GetCells()["B1"].GetValue().AsInteger());
    EXPECT_TRUE(sheet.GetCells()["C1"].GetValue().AsBool());
    EXPECT_EQ(CellValueType::DateTime, sheet.GetCells()["D1"].GetType());
    EXPECT_EQ("", sheet.GetCells()["E1"].GetDisplayStringValue());
}