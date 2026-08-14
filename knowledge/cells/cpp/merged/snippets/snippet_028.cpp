TEST(CellDataGoldenTests, display_runtime_culture_after_roundtrip)
{
    TempDir temp("golden-display-culture");
    const auto path = temp.Path("display-culture.xlsx");
    Workbook workbook;
    auto& sheet = workbook.GetWorksheets()[0];
    const auto timestamp = DateTime(2024, 5, 6, 7, 8, 9);

    sheet.GetCells()["A1"].PutValue(1234.5);
    auto numericStyle = sheet.GetCells()["A1"].GetStyle();
    numericStyle.SetNumberFormat("#,##0.00");
    sheet.GetCells()["A1"].SetStyle(numericStyle);

    sheet.GetCells()["B1"].PutValue(timestamp);
    auto dateStyle = sheet.GetCells()["B1"].GetStyle();
    dateStyle.SetNumberFormat("[$-409]dddd, mmmm d, yyyy");
    sheet.GetCells()["B1"].SetStyle(dateStyle);
    workbook.Save(path.string());

    Workbook loaded(path.string());
    loaded.GetSettings().SetCulture(MakeLocaleStrict({"fr-FR", "fr_FR.UTF-8", "fr_FR"}));
    EXPECT_EQ("1 234,50", loaded.GetWorksheets()[0].GetCells()["A1"].GetDisplayStringValue());
    EXPECT_EQ("Monday, May 6, 2024", loaded.GetWorksheets()[0].GetCells()["B1"].GetDisplayStringValue());
}