TEST(CellDataGoldenTests, formula_cells_persist_formula_and_cached_value)
{
    TempDir temp("golden-formula");
    const auto path = temp.Path("formula.xlsx");
    Workbook workbook;
    auto& sheet = workbook.GetWorksheets()[0];
    sheet.GetCells()["A1"].PutValue(10);
    sheet.GetCells()["B1"].PutValue(20);
    sheet.GetCells()["C1"].PutValue(30);
    sheet.GetCells()["C1"].SetFormula("=A1+B1");
    workbook.Save(path.string());

    const auto worksheetXml = Package::ReadEntryText(path, "xl/worksheets/sheet1.xml");
    EXPECT_TRUE(Contains(worksheetXml, "<f>A1+B1</f>"));
    EXPECT_TRUE(Contains(worksheetXml, "<v>30</v>"));

    Workbook loaded(path.string());
    EXPECT_EQ("=A1+B1", loaded.GetWorksheets()[0].GetCells()["C1"].GetFormula());
    EXPECT_EQ("30", loaded.GetWorksheets()[0].GetCells()["C1"].GetStringValue());
}