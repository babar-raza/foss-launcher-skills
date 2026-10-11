TEST(CellDataUnitTests, displaystringvalue_applies_long_time_and_elapsed_fraction_with_culture)
{
    Workbook workbook;
    workbook.GetSettings().SetCulture(MakeLocaleStrict({"de-DE", "de_DE.UTF-8", "de_DE"}));
    auto& sheet = workbook.GetWorksheets()[0];
    const auto timestamp = DateTime(2024, 5, 6, 7, 8, 9, 345);

    auto longTimeCell = sheet.GetCells()["F4"];
    longTimeCell.PutValue(timestamp);
    auto longTimeStyle = longTimeCell.GetStyle();
    longTimeStyle.SetNumberFormat("[$-F400]");
    longTimeCell.SetStyle(longTimeStyle);

    auto elapsedCell = sheet.GetCells()["G4"];
    elapsedCell.PutValue(timestamp);
    auto elapsedStyle = elapsedCell.GetStyle();
    elapsedStyle.SetNumberFormat("[h]:mm:ss.000");
    elapsedCell.SetStyle(elapsedStyle);

    EXPECT_EQ("07:08:09", longTimeCell.GetDisplayStringValue());
    EXPECT_EQ("7:08:09,345", elapsedCell.GetDisplayStringValue());
}