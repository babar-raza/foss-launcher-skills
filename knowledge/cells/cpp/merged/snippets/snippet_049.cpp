TEST(CellDataUnitTests, stringvalue_formats_supported_scalar_types)
{
    Workbook workbook;
    auto& sheet = workbook.GetWorksheets()[0];
    const auto timestamp = DateTime(2024, 5, 6, 7, 8, 9);

    sheet.GetCells()["A1"].PutValue(true);
    sheet.GetCells()["B1"].PutValue(123);
    sheet.GetCells()["C1"].PutValue(12.5);
    sheet.GetCells()["D1"].PutValue(timestamp);

    EXPECT_EQ("TRUE", sheet.GetCells()["A1"].GetStringValue());
    EXPECT_EQ("TRUE", sheet.GetCells()["A1"].GetDisplayStringValue());
    EXPECT_EQ("123", sheet.GetCells()["B1"].GetStringValue());
    EXPECT_EQ("123", sheet.GetCells()["B1"].GetDisplayStringValue());
    EXPECT_EQ("12.5", sheet.GetCells()["C1"].GetStringValue());
    EXPECT_EQ("12.5", sheet.GetCells()["C1"].GetDisplayStringValue());
    EXPECT_EQ("5/6/2024 7:08", sheet.GetCells()["D1"].GetStringValue());
    EXPECT_EQ("5/6/2024 7:08", sheet.GetCells()["D1"].GetDisplayStringValue());
}