TEST(CellDataUnitTests, style_api_covers_all_public_settings)
{
    Workbook workbook;
    auto primaryCell = workbook.GetWorksheets()[0].GetCells()["A1"];
    primaryCell.PutValue(1);

    auto primaryStyle = primaryCell.GetStyle();
    ApplyPrimaryStyle(primaryStyle);

    auto untouched = primaryCell.GetStyle();
    EXPECT_EQ("Calibri", untouched.GetFont().GetName());
    EXPECT_EQ(FillPattern::None, untouched.GetPattern());
    EXPECT_TRUE(untouched.GetIsLocked());
    EXPECT_FALSE(untouched.GetIsHidden());
    EXPECT_EQ(0, untouched.GetIndentLevel());
    EXPECT_EQ(0, untouched.GetTextRotation());
    EXPECT_EQ(0, untouched.GetReadingOrder());
    EXPECT_FALSE(untouched.GetShrinkToFit());
    EXPECT_FALSE(untouched.GetFont().GetStrikeThrough());
    EXPECT_FALSE(untouched.GetBorders().GetDiagonalUp());
    EXPECT_FALSE(untouched.GetBorders().GetDiagonalDown());
    EXPECT_EQ("General", untouched.GetNumberFormat());

    primaryCell.SetStyle(primaryStyle);
    AssertPrimaryStyle(primaryCell.GetStyle());

    auto mutatedClone = primaryCell.GetStyle();
    auto mutatedFont = mutatedClone.GetFont();
    mutatedFont.SetName("Mutated");
    mutatedFont.SetStrikeThrough(false);
    mutatedClone.SetFont(mutatedFont);
    mutatedClone.SetPattern(FillPattern::None);
    mutatedClone.SetForegroundColor(Color::Empty());
    mutatedClone.SetBackgroundColor(Color::Empty());
    mutatedClone.SetHorizontalAlignment(HorizontalAlignmentType::Left);
    mutatedClone.SetVerticalAlignment(VerticalAlignmentType::Top);
    mutatedClone.SetWrapText(false);
    mutatedClone.SetIndentLevel(0);
    mutatedClone.SetTextRotation(0);
    mutatedClone.SetShrinkToFit(false);
    mutatedClone.SetReadingOrder(0);
    mutatedClone.SetRelativeIndent(0);
    mutatedClone.SetIsLocked(true);
    mutatedClone.SetIsHidden(false);

    auto persistedPrimary = primaryCell.GetStyle();
    EXPECT_EQ("Arial", persistedPrimary.GetFont().GetName());
    EXPECT_TRUE(persistedPrimary.GetFont().GetStrikeThrough());
    EXPECT_EQ(FillPattern::LightGrid, persistedPrimary.GetPattern());
    EXPECT_EQ(BorderStyleType::MediumDashDot, persistedPrimary.GetBorders().GetRight().GetLineStyle());
    EXPECT_EQ(BorderStyleType::SlantedDashDot, persistedPrimary.GetBorders().GetDiagonal().GetLineStyle());
    EXPECT_TRUE(persistedPrimary.GetBorders().GetDiagonalUp());
    EXPECT_TRUE(persistedPrimary.GetBorders().GetDiagonalDown());
    EXPECT_EQ(4, persistedPrimary.GetNumber());
    EXPECT_EQ("#,##0.00", persistedPrimary.GetNumberFormat());
    EXPECT_EQ(HorizontalAlignmentType::Distributed, persistedPrimary.GetHorizontalAlignment());
    EXPECT_EQ(VerticalAlignmentType::Distributed, persistedPrimary.GetVerticalAlignment());
    EXPECT_TRUE(persistedPrimary.GetWrapText());
    EXPECT_EQ(2, persistedPrimary.GetIndentLevel());
    EXPECT_EQ(45, persistedPrimary.GetTextRotation());
    EXPECT_TRUE(persistedPrimary.GetShrinkToFit());
    EXPECT_EQ(2, persistedPrimary.GetReadingOrder());
    EXPECT_EQ(1, persistedPrimary.GetRelativeIndent());
    EXPECT_FALSE(persistedPrimary.GetIsLocked());
    EXPECT_TRUE(persistedPrimary.GetIsHidden());

    auto customCell = workbook.GetWorksheets()[0].GetCells()["B2"];
    auto customStyle = customCell.GetStyle();
    ApplyCustomNumberStyle(customStyle);
    customCell.SetStyle(customStyle);

    AssertCustomNumberStyle(customCell.GetStyle());
    EXPECT_EQ(CellValueType::Blank, customCell.GetType());

    Style numberFormatStyle;
    numberFormatStyle.SetNumberFormat("0.00%");
    EXPECT_EQ(10, numberFormatStyle.GetNumber());
    EXPECT_EQ("", numberFormatStyle.GetCustom());
    numberFormatStyle.SetNumberFormat("[Blue]0.000");
    EXPECT_EQ(0, numberFormatStyle.GetNumber());
    EXPECT_EQ("[Blue]0.000", numberFormatStyle.GetCustom());

    EXPECT_THROW(numberFormatStyle.SetIndentLevel(-1), CellsException);
    EXPECT_THROW(numberFormatStyle.SetTextRotation(181), CellsException);
    EXPECT_THROW(numberFormatStyle.SetReadingOrder(3), CellsException);
}