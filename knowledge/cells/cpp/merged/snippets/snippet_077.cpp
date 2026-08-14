TEST(WorkbookPortingTests, StyleFormattingPersistsThroughXlsxRoundTrip)
{
    TempDir temp;
    const auto path = temp.Path("style.xlsx");

    Workbook workbook;
    auto cell = workbook.GetWorksheets()[0].GetCells()["C4"];
    cell.PutValue(0.125);
    auto style = cell.GetStyle();
    ApplyVisibleStyle(style);
    cell.SetStyle(style);
    workbook.Save(path.string());

    Workbook loaded(path.string());
    auto loadedCell = loaded.GetWorksheets()[0].GetCells()["C4"];
    auto loadedStyle = loadedCell.GetStyle();

    EXPECT_EQ("0.00%", loadedStyle.GetNumberFormat());
    EXPECT_TRUE(loadedStyle.GetFont().GetBold());
    EXPECT_TRUE(loadedStyle.GetFont().GetItalic());
    EXPECT_EQ("Arial", loadedStyle.GetFont().GetName());
    EXPECT_EQ(FillPattern::Solid, loadedStyle.GetPattern());
    EXPECT_EQ("12.50%", loadedCell.GetDisplayStringValue());
}