TEST(CellDataUnitTests, displaystringvalue_uses_workbook_culture_and_locale_directives)
{
    Workbook workbook;
    auto& sheet = workbook.GetWorksheets()[0];
    workbook.GetSettings().SetCulture(MakeLocaleStrict({"fr-FR", "fr_FR.UTF-8", "fr_FR"}));

    auto numeric = sheet.GetCells()["A3"];
    numeric.PutValue(1234.5);
    auto numericStyle = numeric.GetStyle();
    numericStyle.SetNumberFormat("#,##0.00");
    numeric.SetStyle(numericStyle);

    auto dateCell = sheet.GetCells()["B3"];
    const auto timestamp = DateTime(2024, 5, 6, 7, 8, 9);
    dateCell.PutValue(timestamp);
    auto dateStyle = dateCell.GetStyle();
    dateStyle.SetNumberFormat("dddd, mmmm d, yyyy");
    dateCell.SetStyle(dateStyle);

    auto englishDate = sheet.GetCells()["C3"];
    englishDate.PutValue(timestamp);
    auto englishDateStyle = englishDate.GetStyle();
    englishDateStyle.SetNumberFormat("[$-409]dddd, mmmm d, yyyy");
    englishDate.SetStyle(englishDateStyle);

    auto yenCell = sheet.GetCells()["D3"];
    yenCell.PutValue(1234.5);
    auto yenStyle = yenCell.GetStyle();
    yenStyle.SetNumberFormat("[$\xC2\xA5-411]#,##0.00");
    yenCell.SetStyle(yenStyle);

    auto longDateCell = sheet.GetCells()["E3"];
    longDateCell.PutValue(timestamp);
    auto longDateStyle = longDateCell.GetStyle();
    longDateStyle.SetNumberFormat("[$-F800]");
    longDateCell.SetStyle(longDateStyle);

    EXPECT_EQ("1 234,50", numeric.GetDisplayStringValue());
    EXPECT_EQ("lundi, mai 6, 2024", dateCell.GetDisplayStringValue());
    EXPECT_EQ("Monday, May 6, 2024", englishDate.GetDisplayStringValue());
    EXPECT_EQ("\xC2\xA5" "1,234.50", yenCell.GetDisplayStringValue());

    workbook.GetSettings().SetCulture(MakeLocaleStrict({"de-DE", "de_DE.UTF-8", "de_DE"}));
    EXPECT_EQ("Montag, 6. Mai 2024", longDateCell.GetDisplayStringValue());
}