TEST(CompatibilityTests, public_type_mapping_matches_after_roundtrip)
{
    TempDir temp("compat-types");
    const auto path = temp.Path("types.xlsx");
    auto workbook = CreateMixedCellWorkbook();
    workbook.Save(path.string());

    Workbook loaded(path.string());
    EXPECT_EQ(CellValueType::String, loaded.GetWorksheets()[0].GetCells()["A1"].GetType());
    EXPECT_EQ(CellValueType::Number, loaded.GetWorksheets()[0].GetCells()["B1"].GetType());
    EXPECT_EQ(CellValueType::Boolean, loaded.GetWorksheets()[0].GetCells()["C1"].GetType());
    EXPECT_EQ(CellValueType::Number, loaded.GetWorksheets()[0].GetCells()["D1"].GetType());
    EXPECT_EQ(CellValueType::Number, loaded.GetWorksheets()[0].GetCells()["E1"].GetType());
    EXPECT_EQ(CellValueType::DateTime, loaded.GetWorksheets()[0].GetCells()["F1"].GetType());
    EXPECT_EQ(CellValueType::Formula, loaded.GetWorksheets()[0].GetCells()["G1"].GetType());
}