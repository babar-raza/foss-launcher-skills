TEST(CellDataUnitTests, displaystringvalue_applies_date_and_text_formats)
{
    Workbook workbook;
    auto& sheet = workbook.GetWorksheets()[0];
    const auto timestamp = DateTime(2024, 5, 6, 7, 8, 9);

    auto builtInDate = sheet.GetCells()["A2"];
    builtInDate.PutValue(timestamp);
    auto builtInDateStyle = builtInDate.GetStyle();
    builtInDateStyle.SetNumber(14);
    builtInDate.SetStyle(builtInDateStyle);

    auto customDate = sheet.GetCells()["B2"];
    customDate.PutValue(timestamp);
    auto customDateStyle = customDate.GetStyle();
    customDateStyle.SetNumberFormat("d-mmm-yy h:mm AM/PM");
    customDate.SetStyle(customDateStyle);

    auto elapsed = sheet.GetCells()["C2"];
    elapsed.PutValue(timestamp);
    auto elapsedStyle = elapsed.GetStyle();
    elapsedStyle.SetNumber(46);
    elapsed.SetStyle(elapsedStyle);

    auto textCell = sheet.GetCells()["D2"];
    textCell.PutValue("ABC");
    auto textStyle = textCell.GetStyle();
    textStyle.SetNumberFormat("0;0;0;\"Item \"@");
    textCell.SetStyle(textStyle);

    EXPECT_EQ("5/6/2024 7:08", builtInDate.GetStringValue());
    EXPECT_EQ("05-06-24", builtInDate.GetDisplayStringValue());
    EXPECT_EQ("5/6/2024 7:08", customDate.GetStringValue());
    EXPECT_EQ("6-May-24 7:08 AM", customDate.GetDisplayStringValue());
    EXPECT_EQ("5/6/2024 7:08", elapsed.GetStringValue());
    EXPECT_EQ("7:08:09", elapsed.GetDisplayStringValue());
    EXPECT_EQ("ABC", textCell.GetStringValue());
    EXPECT_EQ("Item ABC", textCell.GetDisplayStringValue());
}