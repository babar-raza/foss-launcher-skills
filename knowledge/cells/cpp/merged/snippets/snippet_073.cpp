TEST(WorkbookPortingTests, StyleMutationsRequireSetStyleAndPersistOnCell)
{
    Workbook workbook;
    auto cell = workbook.GetWorksheets()[0].GetCells()["A1"];
    cell.PutValue(0.125);

    auto style = cell.GetStyle();
    ApplyVisibleStyle(style);

    EXPECT_FALSE(cell.GetStyle().GetFont().GetBold());
    EXPECT_EQ("General", cell.GetStyle().GetNumberFormat());

    cell.SetStyle(style);

    auto applied = cell.GetStyle();
    EXPECT_TRUE(applied.GetFont().GetBold());
    EXPECT_TRUE(applied.GetFont().GetItalic());
    EXPECT_EQ("Arial", applied.GetFont().GetName());
    EXPECT_EQ(Color::FromArgb(255, 20, 40, 60), applied.GetFont().GetColor());
    EXPECT_EQ(FillPattern::Solid, applied.GetPattern());
    EXPECT_EQ(Color::FromArgb(255, 250, 230, 100), applied.GetForegroundColor());
    EXPECT_EQ(HorizontalAlignmentType::Center, applied.GetHorizontalAlignment());
    EXPECT_EQ("0.00%", applied.GetNumberFormat());
    EXPECT_EQ("12.50%", cell.GetDisplayStringValue());

    auto clone = cell.GetStyle();
    auto cloneFont = clone.GetFont();
    cloneFont.SetBold(false);
    clone.SetFont(cloneFont);
    EXPECT_TRUE(cell.GetStyle().GetFont().GetBold());
}