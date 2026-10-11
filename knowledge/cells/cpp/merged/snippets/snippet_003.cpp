TEST(CompatibilityTests, formula_setter_accepts_with_or_without_leading_equal)
{
    Workbook workbook;
    auto cell = workbook.GetWorksheets()[0].GetCells()["A1"];
    cell.PutValue(10);
    cell.SetFormula("B1+C1");
    EXPECT_EQ("=B1+C1", cell.GetFormula());

    cell.SetFormula("=D1+E1");
    EXPECT_EQ("=D1+E1", cell.GetFormula());
}