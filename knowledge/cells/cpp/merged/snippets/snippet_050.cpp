TEST(CellDataUnitTests, displaystringvalue_applies_numeric_formats_and_stringvalue_stays_raw)
{
    Workbook workbook;
    auto& sheet = workbook.GetWorksheets()[0];

    auto grouped = sheet.GetCells()["A1"];
    grouped.PutValue(1234.567);
    auto groupedStyle = grouped.GetStyle();
    groupedStyle.SetNumberFormat("#,##0.00");
    grouped.SetStyle(groupedStyle);

    auto percent = sheet.GetCells()["B1"];
    percent.PutValue(0.125);
    auto percentStyle = percent.GetStyle();
    percentStyle.SetNumberFormat("0.00%");
    percent.SetStyle(percentStyle);

    auto scientific = sheet.GetCells()["C1"];
    scientific.PutValue(1234.0);
    auto scientificStyle = scientific.GetStyle();
    scientificStyle.SetNumberFormat("0.00E+00");
    scientific.SetStyle(scientificStyle);

    auto fraction = sheet.GetCells()["D1"];
    fraction.PutValue(1.25);
    auto fractionStyle = fraction.GetStyle();
    fractionStyle.SetNumberFormat("# ?/?");
    fraction.SetStyle(fractionStyle);

    auto negative = sheet.GetCells()["E1"];
    negative.PutValue(-12.3);
    auto negativeStyle = negative.GetStyle();
    negativeStyle.SetNumberFormat("#,##0.00_);(#,##0.00)");
    negative.SetStyle(negativeStyle);

    auto color = sheet.GetCells()["F1"];
    color.PutValue(1.25);
    auto colorStyle = color.GetStyle();
    colorStyle.SetNumberFormat("[Blue]0.000");
    color.SetStyle(colorStyle);

    auto conditionalHigh = sheet.GetCells()["G1"];
    conditionalHigh.PutValue(125.0);
    auto conditionalStyle = conditionalHigh.GetStyle();
    conditionalStyle.SetNumberFormat("[>100]0.0;\"small\"");
    conditionalHigh.SetStyle(conditionalStyle);

    auto conditionalLow = sheet.GetCells()["H1"];
    conditionalLow.PutValue(10.0);
    conditionalLow.SetStyle(conditionalStyle);

    EXPECT_EQ("1234.567", grouped.GetStringValue());
    EXPECT_EQ("1,234.57", grouped.GetDisplayStringValue());
    EXPECT_EQ("0.125", percent.GetStringValue());
    EXPECT_EQ("12.50%", percent.GetDisplayStringValue());
    EXPECT_EQ("1234", scientific.GetStringValue());
    EXPECT_EQ("1.23E+03", scientific.GetDisplayStringValue());
    EXPECT_EQ("1.25", fraction.GetStringValue());
    EXPECT_EQ("1 1/4", fraction.GetDisplayStringValue());
    EXPECT_EQ("-12.3", negative.GetStringValue());
    EXPECT_EQ("(12.30)", negative.GetDisplayStringValue());
    EXPECT_EQ("1.25", color.GetStringValue());
    EXPECT_EQ("1.250", color.GetDisplayStringValue());
    EXPECT_EQ("125", conditionalHigh.GetStringValue());
    EXPECT_EQ("125.0", conditionalHigh.GetDisplayStringValue());
    EXPECT_EQ("10", conditionalLow.GetStringValue());
    EXPECT_EQ("small", conditionalLow.GetDisplayStringValue());
}