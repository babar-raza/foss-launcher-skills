TEST(CellDataUnitTests, displaystringvalue_applies_extended_date_tokens)
{
    Workbook workbook;
    workbook.GetSettings().SetCulture(MakeLocaleStrict({"en-US", "en_US.UTF-8", "en_US", "C"}));
    auto& sheet = workbook.GetWorksheets()[0];
    const auto timestamp = DateTime(2024, 5, 6, 7, 8, 9, 345);

    auto monthInitial = sheet.GetCells()["A4"];
    monthInitial.PutValue(timestamp);
    auto monthInitialStyle = monthInitial.GetStyle();
    monthInitialStyle.SetNumberFormat("mmmmm d, yyyy");
    monthInitial.SetStyle(monthInitialStyle);

    auto abbreviatedDate = sheet.GetCells()["B4"];
    abbreviatedDate.PutValue(timestamp);
    auto abbreviatedStyle = abbreviatedDate.GetStyle();
    abbreviatedStyle.SetNumberFormat("ddd, mmm d yyyy");
    abbreviatedDate.SetStyle(abbreviatedStyle);

    auto fractionalSeconds = sheet.GetCells()["C4"];
    fractionalSeconds.PutValue(timestamp);
    auto fractionalStyle = fractionalSeconds.GetStyle();
    fractionalStyle.SetNumberFormat("h:mm:ss.000 AM/PM");
    fractionalSeconds.SetStyle(fractionalStyle);

    auto shortFraction = sheet.GetCells()["D4"];
    shortFraction.PutValue(timestamp);
    auto shortFractionStyle = shortFraction.GetStyle();
    shortFractionStyle.SetNumberFormat("hh:mm:ss.00");
    shortFraction.SetStyle(shortFractionStyle);

    auto shortAmPm = sheet.GetCells()["E4"];
    shortAmPm.PutValue(timestamp);
    auto shortAmPmStyle = shortAmPm.GetStyle();
    shortAmPmStyle.SetNumberFormat("h A/P");
    shortAmPm.SetStyle(shortAmPmStyle);

    EXPECT_EQ("M 6, 2024", monthInitial.GetDisplayStringValue());
    EXPECT_EQ("Mon, May 6 2024", abbreviatedDate.GetDisplayStringValue());
    EXPECT_EQ("7:08:09.345 AM", fractionalSeconds.GetDisplayStringValue());
    EXPECT_EQ("07:08:09.34", shortFraction.GetDisplayStringValue());
    EXPECT_EQ("7 A", shortAmPm.GetDisplayStringValue());
}