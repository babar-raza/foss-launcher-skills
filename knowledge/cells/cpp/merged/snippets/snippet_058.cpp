TEST(CellDataUnitTests, style_mutation_requires_setstyle_and_returns_clones)
{
    Workbook workbook;
    auto cell = workbook.GetWorksheets()[0].GetCells()["A1"];

    auto style = cell.GetStyle();
    auto font = style.GetFont();
    font.SetBold(true);
    style.SetFont(font);
    style.SetHorizontalAlignment(HorizontalAlignmentType::Right);

    auto untouched = cell.GetStyle();
    EXPECT_FALSE(untouched.GetFont().GetBold());
    EXPECT_EQ(HorizontalAlignmentType::General, untouched.GetHorizontalAlignment());

    cell.SetStyle(style);
    auto applied = cell.GetStyle();
    EXPECT_TRUE(applied.GetFont().GetBold());
    EXPECT_EQ(HorizontalAlignmentType::Right, applied.GetHorizontalAlignment());

    auto appliedFont = applied.GetFont();
    appliedFont.SetItalic(true);
    applied.SetFont(appliedFont);
    EXPECT_FALSE(cell.GetStyle().GetFont().GetItalic());
}